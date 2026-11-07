import os, json, itertools, re
from datetime import date, timedelta
from pathlib import Path
import requests
import streamlit as st

st.set_page_config(page_title='룩선 코디 자동화 MVP', page_icon='🧥', layout='wide')
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

st.title('🧥 룩선 | 코디 자동화 MVP')
st.caption('키워드 추이: NAVER API HUB 실연동 · 에이블리 브랜드 상품: 사용자 제공 JSON · 15만 원 이하 코디 3세트')
with st.sidebar:
    st.header('설정')
    budget=st.number_input('코디 전체 예산 (원)',min_value=10000,value=150000,step=10000)
    warmth=st.slider('목표 보온성',1,10,5)
    style=st.selectbox('스타일',['혼합','미니멀','페미닌','캐주얼','스트릿'])
    n=st.selectbox('코디 세트 수',[3,5,10],index=0)
    st.caption('현재 보온성은 제품 평가 필드와 비교하는 참고 지표이며, 실제 체감 온도를 보장하지 않습니다.')

tab1,tab2,tab3=st.tabs(['① 키워드 분석','② 브랜드 상품 등록','③ 코디 생성'])
