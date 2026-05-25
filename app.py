import streamlit as st
from datetime import datetime
import io
import uuid

import firebase_admin
from firebase_admin import credentials, firestore

import speech_recognition as sr
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


st.set_page_config(
    page_title="나의 일기",
    page_icon="📔",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 700px; }
    .stButton > button { border-radius: 12px; font-weight: 600; }
    h1 { font-size: 1.8rem !important; text-align: center; }
    @media (max-width: 640px) {
        .stTextArea textarea { font-size: 16px !important; }
        .stTextInput input  { font-size: 16px !important; }
    }
</style>
""", unsafe_allow_html=True)


# ── Firebase ──────────────────────────────────────────────────────────────────
def init_firebase():
    if firebase_admin._apps:
        return firestore.client()
    try:
        info = {
            "type":             st.secrets["firebase"]["type"],
            "project_id":       st.secrets["firebase"]["project_id"],
            "private_key_id":   st.secrets["firebase"]["private_key_id"],
            "private_key":      st.secrets["firebase"]["private_key"].replace("\\n", "\n"),
            "client_email":     st.secrets["firebase"]["client_email"],
            "client_id":        st.secrets["firebase"]["client_id"],
            "auth_uri":         "https://accounts.google.com/o/oauth2/auth",
            "token_uri":        "https://oauth2.googleapis.com/token",
        }
        cred = credentials.Certificate(info)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception:
        return None


db = init_firebase()


# ── DB helpers ────────────────────────────────────────────────────────────────
def save_diary(title, content, mood, weather, date_str):
    if not db:
        return False, "Firebase 연결 실패"
    try:
        doc_id = str(uuid.uuid4())
        db.collection("diaries").document(doc_id).set({
            "id":         doc_id,
            "title":      title,
            "content":    content,
            "mood":       mood,
            "weather":    weather,
            "date":       date_str,
            "created_at": datetime.now().isoformat(),
        })
        return True, None
    except Exception as e:
        return False, str(e)


def load_diaries():
    if not db:
        return []
    try:
        docs = db.collection("diaries").order_by(
            "date", direction=firestore.Query.DESCENDING
        ).stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        st.error(f"목록 로드 실패: {e}")
        return []


def delete_diary(doc_id):
    if db:
        db.collection("diaries").document(doc_id).delete()


# ── STT ───────────────────────────────────────────────────────────────────────
def transcribe_audio(audio_file):
    if not PYDUB_AVAILABLE:
        return None, "pydub가 설치되지 않았습니다. `pip install pydub` 실행 후 ffmpeg도 설치해주세요."
    try:
        audio_bytes = audio_file.read()
        segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
        wav_io = io.BytesIO()
        segment.export(wav_io, format="wav")
        wav_io.seek(0)

        r = sr.Recognizer()
        with sr.AudioFile(wav_io) as source:
            data = r.record(source)
        return r.recognize_google(data, language="ko-KR"), None
    except sr.UnknownValueError:
        return None, "음성을 인식하지 못했습니다. 다시 시도해주세요."
    except sr.RequestError as e:
        return None, f"Google STT 오류: {e}"
    except Exception as e:
        return None, f"변환 오류: {e}"


# ── 앱 UI ─────────────────────────────────────────────────────────────────────
st.title("📔 나의 일기")

# Firebase 미설정 안내
if not db:
    st.error("Firebase 설정이 필요합니다.")
    st.markdown("`.streamlit/secrets.toml` 파일을 열어 Firebase 정보를 입력해주세요.")
    with st.expander("secrets.toml 예시 보기"):
        st.code("""
[firebase]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
client_email = "firebase-adminsdk-xxx@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
        """, language="toml")
    st.stop()


MOODS = {
    "💪 뿌듯해":      "proud",
    "😌 평온해":      "calm",
    "🔥 의욕넘쳐":    "motivated",
    "😤 스트레스":    "stressed",
    "🥱 나른해":      "drowsy",
    "😵 정신없어":    "overwhelmed",
    "🫠 번아웃":      "burnout",
    "🥳 신나":        "excited",
    "😬 긴장돼":      "nervous",
    "🫶 감사해":      "grateful",
    "🙃 애매해":      "mixed",
    "😶 멍해":        "blank",
    "😢 속상해":      "sad",
    "😎 쿨해":        "cool",
    "🤩 설레":        "thrilled",
}
WEATHERS = {
    "☀️ 맑음":   "sunny",
    "⛅ 구름":   "cloudy",
    "🌧️ 비":    "rainy",
    "❄️ 눈":    "snowy",
    "🌫️ 흐림":  "foggy",
}
MOOD_EMOJI    = {v: k.split()[0] for k, v in MOODS.items()}
WEATHER_EMOJI = {v: k.split()[0] for k, v in WEATHERS.items()}

tab_write, tab_list = st.tabs(["✏️ 새 일기", "📚 목록 보기"])


# ── 새 일기 ──────────────────────────────────────────────────────────────────
with tab_write:
    if "content_area" not in st.session_state:
        st.session_state.content_area = ""

    selected_date = st.date_input("날짜", value=datetime.today())

    col_mood, col_weather = st.columns(2)
    with col_mood:
        selected_mood = st.selectbox("기분", list(MOODS.keys()))
    with col_weather:
        selected_weather = st.selectbox("날씨", list(WEATHERS.keys()))

    title = st.text_input("제목", placeholder="오늘 하루를 한 줄로 표현해보세요...")

    # 음성 입력
    with st.expander("🎤 음성", expanded=False):
        if not PYDUB_AVAILABLE:
            st.warning("음성 입력을 사용하려면 `pip install pydub` 후 ffmpeg를 설치해주세요.\n\n"
                       "Windows: `winget install ffmpeg`")
        else:
            audio_input = st.audio_input("녹음 버튼을 눌러 말하세요")
            if audio_input:
                if st.button("🔄 텍스트로 변환", use_container_width=True):
                    with st.spinner("음성 인식 중..."):
                        text, err = transcribe_audio(audio_input)
                    if text:
                        sep = " " if st.session_state.content_area else ""
                        st.session_state.content_area += sep + text
                        st.success(f"변환 완료: {text}")
                        st.rerun()
                    else:
                        st.error(err)

    st.text_area(
        "일기 내용",
        placeholder="오늘 어떤 일이 있었나요? 생각이나 느낌을 자유롭게 적어보세요.",
        height=300,
        key="content_area",
        label_visibility="collapsed",
    )

    col_save, col_clear = st.columns([3, 1])
    with col_save:
        if st.button("💾 저장하기", type="primary", use_container_width=True):
            if not title.strip():
                st.error("제목을 입력해주세요.")
            elif not st.session_state.content_area.strip():
                st.error("내용을 입력해주세요.")
            else:
                ok, err = save_diary(
                    title.strip(),
                    st.session_state.content_area.strip(),
                    MOODS[selected_mood],
                    WEATHERS[selected_weather],
                    selected_date.isoformat(),
                )
                if ok:
                    st.success("일기가 저장되었습니다! 📖")
                    st.session_state.content_area = ""
                    st.rerun()
                else:
                    st.error(f"저장 실패: {err}")
    with col_clear:
        if st.button("🗑️ 지우기", use_container_width=True):
            st.session_state.content_area = ""
            st.rerun()


# ── 목록 보기 ─────────────────────────────────────────────────────────────────
with tab_list:
    diaries = load_diaries()

    if not diaries:
        st.info("📝 아직 작성된 일기가 없어요. 첫 번째 일기를 써보세요!")
    else:
        st.markdown(f"총 **{len(diaries)}**개의 일기")
        for diary in diaries:
            date_str    = diary.get("date", "")[:10]
            title_d     = diary.get("title", "제목 없음")
            mood_d      = MOOD_EMOJI.get(diary.get("mood", ""), "")
            weather_d   = WEATHER_EMOJI.get(diary.get("weather", ""), "")
            with st.expander(f"{weather_d} {mood_d} {date_str}  —  {title_d}"):
                st.write(diary.get("content", ""))
                st.caption(f"작성: {diary.get('created_at', '')[:16]}")
                if st.button("삭제", key=f"del_{diary['id']}", type="secondary"):
                    delete_diary(diary["id"])
                    st.rerun()
