import streamlit as st
from supabase import create_client
import google.generativeai as genai
import json
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components

# --- [1. 초기 설정 및 보안] ---
st.set_page_config(page_title="LifeSync | 전인적 목표 관리", page_icon="🔄", layout="wide")

@st.cache_resource
def init_clients():
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    return supabase, model

supabase, model = init_clients()

# --- [2. 핵심 엔진: 고도화된 목표 생성] ---
def generate_hierarchical_roadmap(goal_title):
    prompt = f"""
    목표 '{goal_title}'를 [장기 비전 - 중기 마일스톤 - 단기 실행] 체계로 분석하여 JSON으로 응답하세요.
    
    [가이드라인]
    1. domain: '건강', '커리어', '재테크', '관계', '자기계발', '즐거움' 중 하나 선택.
    2. vision: 1년 뒤의 구체적인 미래 모습.
    3. milestones: 2개의 중기 목표.
    4. actions: 각 마일스톤당 3개의 '단기 실행 과업'. 
       - 매우 구체적이어야 함 (예: '책 읽기' X -> '전략 파트 15p 읽고 핵심 3줄 요약' O)
    
    JSON 형식:
    {{
      "domain": "카테고리",
      "vision": "비전 내용",
      "roadmap": [
        {{ "milestone": "중기 목표", "actions": [ {{ "title": "구체적 과업", "why": "이유", "how": "첫단계" }} ] }}
      ]
    }}
    """
    response = model.generate_content(prompt)
    txt = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(txt)

# --- [3. UI 컴포넌트: 조언자 패널] ---
def render_advisor_panel(act):
    st.subheader(f"💡 AI 조언자의 가이드")
    st.info(f"**과업:** {act['title']}")
    st.write(f"**🎯 왜 중요한가요?**\n{act['advisor_data'].get('why', '성장을 위한 필수 단계입니다.')}")
    st.success(f"**🚀 바로 시작하는 법:** {act['advisor_data'].get('how', '지금 바로 1분만 투자해보세요!')}")
    
    memo = st.text_area("실행 기록 및 메모", value=act['advisor_data'].get('notes', ""), key=f"memo_{act['id']}")
    if st.button("💾 기록 및 상태 업데이트", use_container_width=True):
        new_status = not act['is_completed']
        new_adv = act['advisor_data']
        new_adv['notes'] = memo
        supabase.table("actions").update({"is_completed": new_status, "advisor_data": new_adv}).eq("id", act['id']).execute()
        st.rerun()

# --- [4. 메인 화면 구성] ---
st.sidebar.title("🔄 LifeSync")
menu = st.sidebar.radio("Navigation", ["📊 인생 대시보드", "📅 오늘의 실행", "🎯 로드맵 설계", "🍪 스낵 챌린지"])

# (1) 인생 대시보드 (수레바퀴 & 성취 게이지)
if menu == "📊 인생 대시보드":
    st.header("📊 전인적 성장 대시보드")
    
    goals = supabase.table("goals").select("*").execute().data
    if not goals:
        st.info("아직 데이터가 없습니다. 로드맵을 먼저 설계해보세요!")
    else:
        # 데이터 가공
        df_goals = pd.DataFrame(goals)
        actions = supabase.table("actions").select("goal_id, is_completed").execute().data
        df_actions = pd.DataFrame(actions)
        
        # 카테고리별 성취도 계산
        res = []
        for domain in ['건강', '커리어', '재테크', '관계', '자기계발', '즐거움']:
            domain_goals = df_goals[df_goals['domain'] == domain]
            if not domain_goals.empty:
                d_goal_ids = domain_goals['id'].tolist()
                d_actions = df_actions[df_actions['goal_id'].isin(d_goal_ids)]
                score = (d_actions['is_completed'].sum() / len(d_actions) * 100) if not d_actions.empty else 0
            else: score = 0
            res.append({"Domain": domain, "Score": score})
        
        df_wheel = pd.DataFrame(res)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("🎡 인생의 수레바퀴")
            fig = px.line_polar(df_wheel, r='Score', theta='Domain', line_close=True, range_r=[0, 100])
            fig.update_traces(fill='toself')
            st.plotly_chart(fig, use_container_width=True)
            

        with col2:
            st.subheader("🏆 카테고리별 진행률")
            st.dataframe(df_wheel.sort_values(by="Score", ascending=False), hide_index=True)
            total_prog = df_actions['is_completed'].mean() if not df_actions.empty else 0
            st.metric("전체 인생 동기화 지수", f"{total_prog*100:.1f}%", f"{total_prog*5:.1f}")

# (2) 오늘의 실행 (플로우차트 포함)
elif menu == "📅 오늘의 실행":
    st.header("📅 구체적 실행 센터")
    goals = supabase.table("goals").select("*").execute().data
    if goals:
        selected_g = st.selectbox("집중할 프로젝트", [g['title'] for g in goals])
        target = next(g for g in goals if g['title'] == selected_g)
        
        t1, t2 = st.tabs(["📝 액션 리스트", "🗺️ 로드맵 흐름"])
        actions = supabase.table("actions").select("*").eq("goal_id", target['id']).execute().data
        
        with t1:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.write(f"**Vision:** {target.get('vision', '비전을 향해 나아가세요.')}")
                for a in actions:
                    btn_label = f"{'✅' if a['is_completed'] else '⏳'} {a['title']}"
                    if st.button(btn_label, key=f"act_{a['id']}", use_container_width=True):
                        st.session_state['active_act'] = a
            with c2:
                if 'active_act' in st.session_state:
                    render_advisor_panel(st.session_state['active_act'])

        with t2:
            st.subheader("📍 전략적 흐름도")
            if not actions:
                st.info("과업 데이터가 없습니다.")
            else:
                # 1. Mermaid 문법 생성 (특수문자 제거 강화)
                mermaid_lines = ["graph LR"] # 왼쪽에서 오른쪽으로 흐름
                
                # 목표(비전) 노드
                safe_goal = target['title'].replace('"', "'")
                mermaid_lines.append(f'  Goal(( "{safe_goal}" ))')
                
                # 마일스톤별 그룹화 및 연결
                phases = []
                for a in actions:
                    p_name = a['title'].split(']')[0].replace("[", "").strip()
                    if p_name not in phases:
                        phases.append(p_name)
                
                for i, p in enumerate(phases):
                    safe_p = p.replace('"', "'")
                    mermaid_lines.append(f'  P{i}["{safe_p}"]')
                    if i == 0:
                        mermaid_lines.append(f'  Goal --> P{0}')
                    if i < len(phases) - 1:
                        mermaid_lines.append(f'  P{i} --> P{i+1}')
                
                mermaid_code = "\n".join(mermaid_lines)

                # 2. HTML 렌더링 (CDN 주소와 초기화 로직 보강)
                html_content = f"""
                <div id="graph-container" style="display: flex; justify-content: center; background: white; padding: 20px; border-radius: 10px;">
                    <pre class="mermaid">
                        {mermaid_code}
                    </pre>
                </div>
                <script type="module">
                    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.esm.min.mjs';
                    mermaid.initialize({{ 
                        startOnLoad: true, 
                        theme: 'neutral',
                        securityLevel: 'loose'
                    }});
                    // 명시적 렌더링 호출
                    await mermaid.run();
                </script>
                """
                components.html(html_content, height=400, scrolling=True)

# (3) 로드맵 설계 (Hierarchical)
elif menu == "🎯 로드맵 설계":
    st.header("🎯 장/중/단기 통합 로드맵 설계")
    with st.form("adv_form"):
        g_input = st.text_input("당신의 거대한 꿈은 무엇인가요?")
        btn = st.form_submit_button("AI 정밀 설계 시작")
    
    if btn and g_input:
        with st.spinner("인생의 마일스톤을 계산 중..."):
            data = generate_hierarchical_roadmap(g_input)
            res = supabase.table("goals").insert({
                "title": g_input, 
                "domain": data['domain'], 
                "vision": data['vision']
            }).execute()
            g_id = res.data[0]['id']
            for m in data['roadmap']:
                for a in m['actions']:
                    supabase.table("actions").insert({
                        "goal_id": g_id,
                        "title": f"[{m['milestone']}] {a['title']}",
                        "advisor_data": {"why": a['why'], "how": a['how'], "notes": ""}
                    }).execute()
            st.success("🎯 고도화된 로드맵이 생성되었습니다! 대시보드를 확인하세요.")

# (4) 스낵 챌린지 메뉴 부분
elif menu == "🍪 스낵 챌린지":
    st.header("🍪 LifeSync Snack Bar")
    st.write("당신의 소중한 자투리 시간을 위한 AI 조언자의 맞춤형 제안입니다.")
    
    t_limit = st.select_slider("지금 여유 시간 (분)", options=[1, 5, 10, 15, 20, 30])
    level = st.select_slider("난이도", options=["매우 쉬움", "보통", "도전적"])
    
    if st.button("오늘의 맞춤 스낵 5개 뽑기"):
        with st.spinner("AI 조언자가 당신의 상황에 맞는 활동을 고민 중입니다..."):
            st.session_state['snack_list'] = generate_snack_ai(t_limit, level)
            
    if 'snack_list' in st.session_state:
        for s in st.session_state['snack_list']:
            with st.container(border=True):
                sc1, sc2 = st.columns([4, 1])
                with sc1:
                    st.subheader(f"✨ {s['title']} ({s['duration']})")
                    st.markdown(f"**💡 왜 해야 하나요?**\n{s.get('why', '잠시 숨을 돌리며 에너지를 충전해보세요.')}")
                    st.info(f"**🚀 실천 가이드:** {s.get('how', '지금 바로 시작해보세요!')}")
                
                with sc2:
                    st.write("") # 간격 조절
                    if st.button("완료!", key=f"snk_{s['title']}"):
                        st.balloons()
                        st.toast(f"'{s['title']}' 완료! 당신의 삶이 한 뼘 더 성장했습니다.")
