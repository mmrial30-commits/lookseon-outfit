import os, json, itertools, re
from datetime import date, timedelta
from pathlib import Path
import requests
import streamlit as st

st.set_page_config(page_title='LOOKSEON | Outfit Studio', page_icon='🎀', layout='wide')
BASE=Path(__file__).parent
KEYWORDS=['11월 여자 코디','초겨울 여자 코디','울 코트 코디','여자 겨울 데일리룩','핑크 코트 코디','브라운 코디','여자 니트 코디','코듀로이 팬츠 코디','여자 경량패딩 코디','여자 가디건 코디','여자 머플러 코디','겨울 출근룩']
CATS=['아우터','상의','하의','신발','가방']
PALETTE={'아이보리','크림','화이트','차콜','그레이','블랙','브라운','베이지','핑크','스카이블루','네이비'}

def trend_fetch(keywords, client_id, secret, days=60):
    if not client_id or not secret: raise ValueError('NAVER API HUB 인증정보를 입력하세요.')
    end=date.today()-timedelta(days=1); start=end-timedelta(days=days-1)
    results={}
    # Compare all terms to the same anchor so relative indices are comparable.
    anchor=keywords[0]
    for i in range(0,len(keywords),4):
        group=keywords[i:i+4]
        names=list(dict.fromkeys([anchor]+group))[:5]
        body={'startDate':start.isoformat(),'endDate':end.isoformat(),'timeUnit':'date','keywordGroups':[{'groupName':k,'keywords':[k]} for k in names], 'device':'mo'}
        r=requests.post('https://naverapihub.apigw.ntruss.com/search-trend/v1/search',headers={'X-NCP-APIGW-API-KEY-ID':client_id,'X-NCP-APIGW-API-KEY':secret,'Content-Type':'application/json'},json=body,timeout=25)
        r.raise_for_status()
        for entry in r.json().get('results',[]):
            vals=[float(x['ratio']) for x in entry.get('data',[])]
            recent=sum(vals[-7:])/max(1,len(vals[-7:]))
            previous=sum(vals[-14:-7])/max(1,len(vals[-14:-7]))
            results[entry['title']]={'최근7일지수':round(recent,2),'전주대비%':round((recent-previous)/previous*100,1) if previous else None,'일별':entry.get('data',[])}
    # Ratios from different requests are NOT directly comparable. Only trend growth is ranked across batches.
    return results

def safe_products(data):
    if not isinstance(data,list): raise ValueError('상품 JSON은 배열이어야 합니다.')
    out=[]
    for n,p in enumerate(data):
        if not isinstance(p,dict): continue
        try:
            price=int(p['price']); cat=str(p['category']); url=str(p['url'])
            if cat not in CATS or price<=0 or not url.startswith('https://'): continue
            if p.get('source','')!='에이블리 브랜드': continue
            out.append({**p,'price':price,'id':str(p.get('id',n)),'warmth':max(1,min(10,int(p.get('warmth',5)))),'lightness':max(1,min(10,int(p.get('lightness',5)))),'softness':max(1,min(10,int(p.get('softness',5)))),'rank':int(p.get('rank',9999))})
        except (KeyError,ValueError,TypeError): continue
    return out

def compatibility(items, style, target_warmth=5):
    colors=[p.get('color','') for p in items]
    neutral={'아이보리','크림','화이트','차콜','그레이','블랙','브라운','베이지','네이비'}
    neutral_count=sum(c in neutral for c in colors)
    color_score=10 if neutral_count>=3 else 6 if neutral_count>=2 else 2
    warmth=sum(p['warmth'] for p in items)/len(items)
    lightness=sum(p['lightness'] for p in items)/len(items)
    softness=sum(p['softness'] for p in items)/len(items)
    styles=[str(p.get('style','')) for p in items]
    style_score=sum(style in x for x in styles) if style!='혼합' else len(set(styles))
    ranking=sum(max(0,15-min(p['rank'],15)) for p in items)/len(items)
    return round(color_score*2 + (10-abs(warmth-target_warmth))*2 + lightness*1.5 + softness*1.5 + style_score*2 + ranking,2)

def outfits(products,budget,style,n=3,target_warmth=5):
    groups={cat:[p for p in products if p['category']==cat] for cat in CATS}
    if any(not groups[c] for c in CATS): return [],'아우터·상의·하의·신발·가방 5개 카테고리에 각각 1개 이상 필요합니다.'
    candidates=[]
    for items in itertools.product(*(groups[c][:25] for c in CATS)):
        total=sum(p['price'] for p in items)
        if total>budget: continue
        score=compatibility(items,style,target_warmth)
        candidates.append((score,total,items))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    selected=[]; used=set()
    for score,total,items in candidates:
        ids={p['id'] for p in items}
        if selected and len(ids-used)<2: continue
        selected.append({'score':score,'total':total,'items':list(items)})
        used.update(ids)
        if len(selected)>=n: break
    return selected, '' if selected else '15만 원 이내 완성 코디가 없습니다. 상품 후보나 예산을 조정해 주세요.'

def blog_text(keyword, outfit):
    items={p['category']:p for p in outfit['items']}
    title=f'{keyword}, 가볍고 포근하게 입는 데일리룩 3가지 포인트'
    lines=[f'# {title}','', '[📷 코디 대표 이미지]','',f'이번에는 {keyword}를 주제로 가볍고 따뜻하게 입을 수 있는 조합을 준비했습니다.','',f"{items['아우터']['name']}에 {items['상의']['name']}를 매치하고, {items['하의']['name']}로 전체적인 실루엣을 정리했어요.",'', '[📷 상반신·하의 디테일]','',f"신발은 {items['신발']['name']}, 가방은 {items['가방']['name']}로 마무리했습니다. 전체 가격은 {outfit['total']:,}원입니다.",'','아침저녁 일교차가 큰 날에는 하의에 발열내의를 더하거나 머플러를 함께 착용하는 걸 추천드려요!','','## 착장 정보']
    for cat,p in items.items(): lines.extend([f"**{cat} | {p['brand']} {p['name']} — {p['price']:,}원**",p['url'],''])
    lines+=['*가격과 재고는 확인 시점에 따라 달라질 수 있습니다. 상품 링크에서 최신 정보를 확인해 주세요.*','*제휴 링크가 포함된 경우 관련 고지 문구를 추가해 주세요.*','*AI 착장 이미지를 사용했다면 AI 제작 사실을 표시해 주세요.*']
    return '\n'.join(lines)


# UI-only redesign: API calls and outfit scoring are retained from the MVP.
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Gowun+Dodum&display=swap');
:root{--pink:#ed8fb3;--berry:#a84e72;--blush:#fff0f5;--cream:#fffaf7;--ink:#58434b}
html,body,[class*="css"], [data-testid="stApp"]{font-family:'DM Sans','Gowun Dodum',sans-serif;color:var(--ink)}
[data-testid="stAppViewContainer"]{background:linear-gradient(130deg,#fffafc 0%,#fffdfb 52%,#fdf3f5 100%)}
[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1130px;padding-top:2.2rem;padding-bottom:5rem}
[data-testid="stSidebar"]{background:#fff3f6;border-right:1px solid #f2dbe3}
[data-testid="stSidebar"] .block-container{padding-top:1.7rem}
h1,h2,h3{color:#6e4658!important;letter-spacing:-.035em}
h1{font-size:2.25rem!important}h2{font-size:1.5rem!important}h3{font-size:1.17rem!important}
[data-testid="stTabs"] [data-baseweb="tab-list"]{gap:10px;border-bottom:1px solid #f1d9e1;padding-bottom:12px;flex-wrap:wrap}
button[data-baseweb="tab"]{background:#fff;border:1px solid #f1dbe3;border-radius:13px;padding:9px 16px;color:#88616f;font-weight:650}
button[data-baseweb="tab"][aria-selected="true"]{background:#f9dce7;color:#82445d;border-color:#eeb7cb}
.stButton>button[kind="primary"], .stDownloadButton>button[kind="primary"]{background:#b96888!important;color:white!important;border:0!important}
.stButton>button,.stDownloadButton>button{border-radius:12px!important;min-height:40px;border-color:#eacbd5;color:#92516d}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:#c57d9a;color:#9b4268}
[data-testid="stMetric"]{background:#fff;border:1px solid #f1dce3;border-radius:16px;padding:15px 18px;box-shadow:0 5px 18px #eeb8cd14}
[data-testid="stMetricLabel"]{color:#8f6a78}[data-testid="stMetricValue"]{color:#9e5472}
[data-testid="stAlert"]{border-radius:13px}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input{background:#fffdfd;border-radius:12px}
[data-testid="stDataFrame"]{border:1px solid #f0dbe2;border-radius:14px;overflow:hidden}
[data-testid="stExpander"]{background:#fff;border:1px solid #f1dce3;border-radius:13px}
.pink-hero{background:linear-gradient(115deg,#fff0f5,#fffaf7);border:1px solid #efd2de;border-radius:22px;padding:24px 28px;margin-bottom:18px;box-shadow:0 10px 35px #dd9eb719}
.pink-eyebrow{color:#b76e8a;letter-spacing:.15em;font-size:12px;font-weight:750;margin-bottom:8px}
.pink-title{font-size:32px;font-weight:800;color:#714557;letter-spacing:-.045em;line-height:1.25}
.pink-sub{font-size:13px;color:#947682;margin-top:8px}
.pink-section{font-size:21px;font-weight:750;color:#754b5c;margin:16px 0 8px}
.pink-card{background:#fff;border:1px solid #f0dce4;border-radius:16px;padding:16px 19px;margin:8px 0 14px;box-shadow:0 4px 15px #dfadc017}
.pink-tag{display:inline-block;background:#fce5ed;color:#a45a78;border-radius:20px;padding:5px 10px;font-size:12px;font-weight:650}
.pink-note{font-size:12px;color:#947783;margin:8px 0 16px}
.pink-divider{border-top:1px solid #f0dbe2;margin:18px 0}
@media(max-width:680px){.block-container{padding:1rem .8rem 3rem}.pink-hero{padding:18px}.pink-title{font-size:25px}}
</style>""",unsafe_allow_html=True)

st.markdown("""<div class="pink-hero"><div class="pink-eyebrow">✦ LOOKSEON · OUTFIT STUDIO ✦</div><div class="pink-title">🎀 오늘의 코디, 더 가볍게</div><div class="pink-sub">검색 트렌드부터 브랜드 상품, 데일리룩 조합까지 한 곳에서 · 나만의 코디 작업실 ♡</div></div>""",unsafe_allow_html=True)
with st.sidebar:
    st.markdown('### ♡ My wardrobe')
    budget=st.number_input('코디 전체 예산 (원)',min_value=10000,value=150000,step=10000)
    warmth=st.slider('목표 보온성',1,10,5)
    style=st.selectbox('스타일',['혼합','미니멀','페미닌','캐주얼','스트릿'])
    n=st.selectbox('코디 세트 수',[3,5,10],index=0)
    st.caption('✧ 보온성은 제품 평가 기준이며 실제 체감 온도를 보장하지 않아요.')
    st.markdown('---')
    st.caption('LOOKSEON STUDIO  ·  made for everyday looks ♡')

tab1,tab2,tab3=st.tabs(['♡ 01 · 키워드 발견','✿ 02 · 브랜드 옷장','✧ 03 · 코디 만들기'])
with tab1:
    st.markdown('<div class="pink-section">⌕ 네이버 검색어 트렌드</div>',unsafe_allow_html=True)
    st.caption('입력한 후보 키워드의 모바일 검색 추이를 비교해요. 자동 인기 검색어 발굴이나 절대 검색량 순위는 아닙니다.')
    try:
        cid=st.secrets.get('NAVER_CLIENT_ID','')
        sec=st.secrets.get('NAVER_CLIENT_SECRET','')
    except Exception:
        cid=os.getenv('NAVER_CLIENT_ID','')
        sec=os.getenv('NAVER_CLIENT_SECRET','')
    if cid and sec: st.success('♡ 네이버 데이터랩 연결 준비 완료')
    else: st.warning('Streamlit 앱 Settings → Secrets에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 등록해 주세요.')
    with st.expander('✎ 비교할 키워드 편집',expanded=('trends' not in st.session_state)):
        keys=st.text_area('한 줄에 하나씩 입력',value='\n'.join(KEYWORDS),height=210,key='keyword_input')
    if st.button('✧ 검색 트렌드 분석하기',type='primary',use_container_width=True):
        try:
            kk=list(dict.fromkeys(x.strip() for x in keys.splitlines() if x.strip()))
            if len(kk)<2: st.warning('키워드를 2개 이상 입력해 주세요.')
            else:
                with st.spinner('네이버 데이터 확인 중...'): data=trend_fetch(kk,cid,sec)
                st.session_state['trends']=data
                st.success('♡ 실제 네이버 데이터 수신 완료')
        except Exception as e: st.error(f'조회 실패: {e}')
    if 'trends' in st.session_state:
        data=st.session_state['trends']
        rows=[{'키워드':k,'최근 7일 상대지수':v['최근7일지수'],'전주 대비 증감률 (%)':v['전주대비%']} for k,v in data.items()]
        rows.sort(key=lambda x:x['전주 대비 증감률 (%)'] if x['전주 대비 증감률 (%)'] is not None else -999,reverse=True)
        valid=[r for r in rows if r['전주 대비 증감률 (%)'] is not None]
        best=valid[0] if valid else None
        c1,c2,c3=st.columns(3)
        c1.metric('분석한 키워드',f'{len(rows)}개')
        c2.metric('전주 대비 상승',f"{sum(r['전주 대비 증감률 (%)']>0 for r in valid)}개")
        c3.metric('상승률 1위',best['키워드'] if best else '집계 불가')
        st.markdown('<div class="pink-section">✿ 이번 주 키워드 리포트</div>',unsafe_allow_html=True)
        # st.table renders all rows without a nested vertical scrollbar.
        # Dynamic height for dataframes prevents the internal scroll at ordinary row counts.
        import pandas as pd
        df=pd.DataFrame(rows)
        df['전주 대비 증감률 (%)']=df['전주 대비 증감률 (%)'].map(lambda x: '—' if x is None else f'{x:+.1f}%')
        st.table(df.set_index('키워드'))
        st.caption('※ 다른 API 요청 배치의 상대지수는 직접 비교할 수 없어요. 상승률 기준 정렬이며 검색량 순위가 아닙니다. 이전 주 데이터가 0이면 증감률을 —로 표시합니다.')
        st.download_button('↓ 키워드 리포트 CSV 저장',data=pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'),file_name='lookseon_keyword_report.csv',mime='text/csv')
        st.session_state['keyword_choice']=[x['키워드'] for x in rows]
with tab2:
    st.markdown('<div class="pink-section">♧ 브랜드 옷장 채우기</div>',unsafe_allow_html=True)
    st.caption('에이블리 브랜드 상품의 실제 가격과 링크를 등록하면 코디 조합에 사용해요.')
    st.info('현재 자동 상품 수집은 지원하지 않습니다. 샘플은 가상 상품이므로 실제 구매 링크로 사용하면 안 됩니다.')
    sample_path=BASE/'sample_products.json'
    sample=json.loads(sample_path.read_text(encoding='utf-8')) if sample_path.exists() else []
    uploaded=st.file_uploader('상품 JSON 파일 가져오기',type=['json'])
    with st.expander('✎ 상품 JSON 직접 편집',expanded=False):
        manual=st.text_area('상품 목록',value=json.dumps(sample,ensure_ascii=False,indent=2),height=260)
    if st.button('♡ 상품 검증하고 등록',type='primary'):
        try:
            raw=uploaded.getvalue().decode('utf-8') if uploaded else manual
            products=safe_products(json.loads(raw))
            st.session_state['products']=products
            st.success(f'{len(products)}개 상품 등록 완료')
        except Exception as e: st.error(f'상품 등록 실패: {e}')
    if sample:
        st.download_button('↓ 상품 등록 양식 다운로드',data=json.dumps(sample,ensure_ascii=False,indent=2),file_name='sample_products.json',mime='application/json')
    if 'products' in st.session_state:
        products=st.session_state['products']
        c1,c2=st.columns(2)
        c1.metric('등록된 상품',f'{len(products)}개')
        c2.metric('채워진 카테고리',f"{len(set(p['category'] for p in products))}/5")
        import pandas as pd
        display=pd.DataFrame([{'카테고리':p['category'],'브랜드':p.get('brand',''),'상품명':p.get('name',''),'가격':p['price']} for p in products])
        if not display.empty:
            st.table(display.set_index('카테고리'))
with tab3:
    st.markdown('<div class="pink-section">✧ 나만의 데일리룩 만들기</div>',unsafe_allow_html=True)
    st.caption('아우터·상의·하의·신발·가방을 예산 내에서 조합해요. 실제 상품 데이터가 먼저 필요합니다.')
    products=st.session_state.get('products',[])
    available=st.session_state.get('keyword_choice',KEYWORDS)
    keyword=st.selectbox('블로그 메인 키워드',available)
    c1,c2,c3=st.columns(3)
    c1.metric('예산',f'{budget:,}원')
    c2.metric('보온성',f'{warmth}/10')
    c3.metric('코디 수',f'{n}세트')
    if st.button('🎀 코디 3초 조합하기',type='primary',use_container_width=True):
        if not products: st.error('② 브랜드 옷장에서 실제 상품을 먼저 등록해 주세요.')
        elif any(p.get('demo',False) for p in products): st.error('가상 샘플 상품이 포함되어 있어요. 실제 에이블리 브랜드 상품으로 바꿔주세요.')
        else:
            found,msg=outfits(products,budget,style,n,target_warmth=warmth)
            st.session_state['outfits']=found
            if msg: st.warning(msg)
    for i,o in enumerate(st.session_state.get('outfits',[]),1):
        st.markdown(f'<div class="pink-card"><span class="pink-tag">LOOK {i:02d}</span> &nbsp; <b>{o["total"]:,}원</b> · 매칭 점수 {o["score"]}</div>',unsafe_allow_html=True)
        for p in o['items']:
            st.markdown(f"**{p['category']}** · {p.get('brand','')} {p.get('name','')} · {p['price']:,}원 · [상품 보기]({p['url']})")
        post=blog_text(keyword,o)
        with st.expander(f'✎ LOOK {i} 블로그 원고 미리보기'):
            st.text_area('블로그 원고',post,height=260,key=f'post{i}')
        st.download_button(f'↓ LOOK {i} 블로그 초안',data=post,file_name=f'lookseon_look{i}.md',mime='text/markdown',key=f'dl{i}')
    if st.session_state.get('outfits'):
        st.download_button('↓ 전체 코디 JSON 저장',json.dumps(st.session_state['outfits'],ensure_ascii=False,indent=2),file_name='lookseon_outfits.json',mime='application/json')
