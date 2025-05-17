# backend/app.py

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import random
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func 
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from dotenv import load_dotenv
from datetime import datetime

# --- Configurações da Aplicação ---
app = Flask(__name__)
load_dotenv() 
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# --- Configurações do Banco de Dados ---
# ATUALIZADO: Caminho explícito para o banco de dados na pasta 'backend'
db_path = os.path.join(os.path.dirname(__file__), 'tinder_gamer.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-super-secret-key-gg-v11') # Mude no .env

# --- Configurações do Gemini ---
model_gemini = None

db = SQLAlchemy(app)
jwt = JWTManager(app)

# --- Modelos de Dados (SQLAlchemy) ---
# (User, UserProfile, Like, MatchRating - permanecem os mesmos da versão anterior)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile = db.relationship('UserProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    likes_given = db.relationship('Like', foreign_keys='Like.liker_user_id', backref='liker', lazy='dynamic', cascade="all, delete-orphan")
    likes_received = db.relationship('Like', foreign_keys='Like.liked_user_id', backref='liked', lazy='dynamic', cascade="all, delete-orphan")
    ratings_given = db.relationship('MatchRating', foreign_keys='MatchRating.rater_user_id', backref='rater_user', lazy='dynamic', cascade="all, delete-orphan")
    ratings_received = db.relationship('MatchRating', foreign_keys='MatchRating.rated_user_id', backref='rated_user', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    nome_display = db.Column(db.String(100), default="Jogador")
    jogo_principal = db.Column(db.String(100))
    nivel_de_habilidade = db.Column(db.String(50))
    estilo_jogo = db.Column(db.String(100))
    disponibilidade = db.Column(db.String(200))
    gender = db.Column(db.String(50)) 
    communication_style = db.Column(db.String(100)) 
    profile_complete = db.Column(db.Boolean, default=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    liker_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    liked_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('liker_user_id', 'liked_user_id', name='_liker_liked_uc'),)

class MatchRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rater_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rated_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) 
    game_played = db.Column(db.String(100), nullable=True) 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('rater_user_id', 'rated_user_id', 'game_played', name='_rater_rated_game_uc'),)


# --- Lógica de Inicialização de Serviços ---
def inicializar_servicos_google():
    global model_gemini
    try:
        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            model_gemini = genai.GenerativeModel('gemini-1.5-flash-latest')
            print("Modelo Gemini carregado com sucesso usando GEMINI_API_KEY.")
        else:
            print("ERRO CRÍTICO: GEMINI_API_KEY não configurada. Chatbot não funcionará com IA.")
    except Exception as e:
        print(f"Erro ao carregar o modelo Gemini: {e}")

# --- Lógica do Chatbot de Perfil (Expandida e Corrigida) ---
user_chatbot_state = {} 
PROFILE_QUESTIONS_ORDER = ['nome_display', 'jogo_principal', 'nivel_de_habilidade', 'estilo_jogo', 'disponibilidade', 'gender', 'communication_style']
PROFILE_GEMINI_EXTRACTION_FIELDS = {
    'nome_display': "Nome de display ou apelido do jogador", 'jogo_principal': "Principal jogo de interesse do jogador",
    'nivel_de_habilidade': "Nível de habilidade do jogador no jogo principal", 'estilo_jogo': "Estilo de jogo preferido do jogador",
    'disponibilidade': "Disponibilidade geral do jogador para jogar", 'gender': "Identidade de gênero do jogador",
    'communication_style': "Preferência de comunicação do jogador durante o jogo (ex: no silêncio, conversa, vale tudo cantar e zoar)"
}
PROFILE_GEMINI_CATEGORIES = {
    'nivel_de_habilidade': ['Iniciante', 'Casual', 'Intermediário', 'Avançado', 'Competitivo/Pro', 'Ainda aprendendo', 'Jogo por diversão', 'Mediano', 'Sou tryhard', 'Sou pro player', 'Comecei agora'],
    'estilo_jogo': ['Focado em Diversão/Casual', 'Competitivo/Subir de Ranking', 'Completar Missões/História', 'Explorar Mundos', 'Socializar com amigos', 'Variado/Depende do humor', 'Tryhard'],
    'gender': ['Mulher', 'Homem', 'Não-binário', 'Gênero fluido', 'Agênero', 'Prefiro não dizer', 'Outro'],
    'communication_style': ['No silêncio (foco total)', 'Só o necessário (calls estratégicas)', 'Conversa casual e social', 'Vale tudo (cantar, zoar, resenha!)', 'Depende do momento/jogo', 'Com música e zoeira']
}
BASE_QUESTION_IDEAS = {
    'greeting': "E aí! Sou o GG, seu guia gente boa pra montar um perfil gamer daora e achar seu squad perfeito! Para começar,",
    'nome_display': "como a galera te chama nas partidas, ou qual seu nick preferido?",
    'jogo_principal': "show de bola, {nome_display}! E qual é O JOGO que tá na sua mira agora, aquele que você mais quer encontrar uma galera pra fechar time?",
    'nivel_de_habilidade': "entendi! No {jogo_principal}, você se considera mais tranquilo(a), pegando as manhas, ou já é praticamente uma lenda viva?",
    'estilo_jogo': "massa! E no {jogo_principal}, qual é a sua pegada? Mais pra se divertir e dar umas boas risadas, pra competir valendo e subir no ranking, ou focado em zerar o game e fazer todas as missões?",
    'disponibilidade': "daora! E falando em jogatina, quando é que geralmente pinta aquele seu tempo livre pra detonar nos games?",
    'gender': "pra gente se conhecer um pouquinho melhor e ajudar a encontrar o pessoal certo pra você, como você se identifica em termos de gênero? (Ex: Mulher, Homem, Não-binário, etc. Fique à vontade pra responder como se sentir melhor!)",
    'communication_style': "e pra fechar com chave de ouro: durante a partida, como você curte a comunicação? Mais na concentração total no game, só o essencial pra estratégia, uma resenha de boa com a galera, ou aquele caos divertido com música e muita zoeira?",
    'final': "Aí sim, {nome_display}! Seu perfil gamer tá completíssimo e no jeito! GG WP! Agora é só partir pro abraço e encontrar seus novos parceiros de jogatina!"
}
BOT_PERSONALITY_PROMPT = "Você é GG, um mascote e assistente gamer gente boa, amigável, um pouco divertido, mas principalmente natural e prestativo. Use uma linguagem informal e clara, como se estivesse conversando com um amigo sobre jogos. Use emojis com moderação para dar um toque amigável (😊, 👍, 😉, 🎉, 🤔). Evite gírias muito específicas ou em excesso. Mantenha as perguntas e comentários curtos (uma ou duas frases) e diretos. NÃO repita saudações. Se o usuário der uma resposta, faça um breve comentário de reconhecimento (ex: 'Entendi!', 'Legal!') ANTES da próxima pergunta. Se não entender ou a extração for 'Não especificado', peça para repetir ou ofereça opções."

def generate_bot_question(current_field_to_ask, previous_user_response, collected_data, is_first_interaction_of_session):
    if not model_gemini: 
        fallback_question_idea = BASE_QUESTION_IDEAS.get(current_field_to_ask, "Pode me falar mais sobre isso?")
        if is_first_interaction_of_session: return f"{BASE_QUESTION_IDEAS['greeting']} {fallback_question_idea.format(**collected_data)}"
        return fallback_question_idea.format(**collected_data)
    prompt_parts = [BOT_PERSONALITY_PROMPT]
    base_idea_for_question = BASE_QUESTION_IDEAS[current_field_to_ask].format(**collected_data)
    if is_first_interaction_of_session:
        prompt_parts.append(f"Esta é a primeira pergunta após a saudação. Formule a pergunta para: '{PROFILE_GEMINI_EXTRACTION_FIELDS[current_field_to_ask]}'. Ideia: \"{base_idea_for_question}\". Pergunta:")
    else:
        if previous_user_response: prompt_parts.append(f"User: \"{previous_user_response}\". Comente brevemente e então,")
        context_str = "Considerando"
        if 'nome_display' in collected_data and collected_data['nome_display'] not in ["Não especificado", ""]: context_str += f" (nome: {collected_data['nome_display']})"
        if 'jogo_principal' in collected_data and collected_data['jogo_principal'] not in ["Não especificado", ""] and current_field_to_ask != 'jogo_principal': context_str += f" (joga: {collected_data['jogo_principal']})"
        prompt_parts.append(f"{context_str if len(context_str) > len('Considerando') else ''}, formule a pergunta para: '{PROFILE_GEMINI_EXTRACTION_FIELDS[current_field_to_ask]}'. Ideia: \"{base_idea_for_question}\". Pergunta Gerada:")
    full_prompt = "\n".join(prompt_parts)
    try:
        response = model_gemini.generate_content(full_prompt); question = response.text.strip()
        if question.lower().startswith("pergunta gerada:"): question = question.split(":",1)[-1].strip()
        return question if question else base_idea_for_question
    except Exception as e: print(f"Erro Gemini (gerar pergunta) '{current_field_to_ask}': {e}"); return base_idea_for_question

def extrair_info_chatbot_com_gemini(texto_usuario, campo_desejado):
    if not model_gemini: print("AVISO: Modelo Gemini não carregado para extração."); return texto_usuario 
    categorias = PROFILE_GEMINI_CATEGORIES.get(campo_desejado); pfd = PROFILE_GEMINI_EXTRACTION_FIELDS.get(campo_desejado, campo_desejado)
    prompt = f"Do texto: \"{texto_usuario}\", extraia APENAS: '{pfd}'."
    if categorias: prompt += f"\nCategorias: {categorias}. Se não claro/encaixar, retorne 'Não especificado'."
    else: prompt += f"\nRetorne conciso. Se não claro, 'Não especificado'."
    prompt += f"\nRetorne APENAS o valor para '{pfd}':"
    try:
        response = model_gemini.generate_content(prompt); info_extraida = response.text.strip()
        if ":" in info_extraida and info_extraida.lower().startswith(pfd.lower().split()[0].lower()): info_extraida = info_extraida.split(":", 1)[-1].strip()
        if not info_extraida or "não especificado" in info_extraida.lower() or "não identificar" in info_extraida.lower() or len(info_extraida) > 100: return "Não especificado"
        return info_extraida
    except Exception as e: print(f"Erro API Gemini ao extrair ('{campo_desejado}'): {e}"); return texto_usuario

@app.route('/chatbot/message', methods=['POST'])
@jwt_required()
def chatbot_message():
    current_user_id_str = get_jwt_identity(); current_user_id = int(current_user_id_str)
    data = request.json; user_message = data.get('message', '').strip()
    if current_user_id not in user_chatbot_state: user_chatbot_state[current_user_id] = {'current_question_idx': 0, 'collected_data': {}, 'last_user_response': None}
    state = user_chatbot_state[current_user_id]; question_idx = state['current_question_idx']
    is_first_call = (question_idx == 0 and not user_message and not state['collected_data'])
    if not is_first_call and question_idx > 0 : 
        prev_idx = question_idx -1 
        if prev_idx < len(PROFILE_QUESTIONS_ORDER):
            prev_field = PROFILE_QUESTIONS_ORDER[prev_idx]
            extracted = extrair_info_chatbot_com_gemini(user_message, prev_field)
            state['collected_data'][prev_field] = extracted
            print(f"U{current_user_id} C'{prev_field}':R'{user_message}',E'{extracted}'")
    state['last_user_response'] = user_message if user_message else state['last_user_response']
    if question_idx < len(PROFILE_QUESTIONS_ORDER): 
        current_field = PROFILE_QUESTIONS_ORDER[question_idx]
        prev_resp_for_comment = state['last_user_response'] if question_idx > 0 else None
        bot_q = generate_bot_question(current_field, prev_resp_for_comment, state['collected_data'], question_idx == 0)
        state['current_question_idx'] += 1
        return jsonify({"bot_response":bot_q, "profile_complete":False})
    else:
        up = UserProfile.query.filter_by(user_id=current_user_id).first()
        if not up: up=UserProfile(user_id=current_user_id);db.session.add(up)
        for f in PROFILE_QUESTIONS_ORDER: 
            val = state['collected_data'].get(f)
            if val is not None and val.strip() != "": setattr(up, f, val)
            elif getattr(up, f, None) is None : setattr(up, f, "Não especificado")
        up.profile_complete=True
        try: 
            db.session.commit();nf=state['collected_data'].get('nome_display','Jogador(a)')
            if nf == "Não especificado" or not nf: nf = User.query.get(current_user_id).username
            fm=BASE_QUESTION_IDEAS['final'].format(nome_display=nf)
            if current_user_id in user_chatbot_state:del user_chatbot_state[current_user_id]
            return jsonify({"bot_response":fm,"profile_complete":True,"profile_data":state['collected_data']})
        except Exception as e: 
            db.session.rollback();print(f"Erro salvar perfil U{current_user_id}:{e}")
            return jsonify({"bot_response":"Ops! Erro ao salvar.","profile_complete":False,"error":str(e)}),500

# --- Endpoints de Autenticação (Expandidos para Clareza) ---
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json; username = data.get('username'); email = data.get('email'); password = data.get('password')
    if not username or not email or not password: return jsonify({"msg": "Faltam dados"}), 400
    if User.query.filter((User.username == username) | (User.email == email)).first(): return jsonify({"msg": "Usuário ou email já existe"}), 409
    new_user = User(username=username, email=email); new_user.set_password(password)
    db.session.add(new_user); db.session.commit(); return jsonify({"msg": "Usuário cadastrado!"}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    print("DEBUG: Rota /auth/login acessada.") 
    data = request.json; print(f"DEBUG: Dados recebidos: {data}") 
    if not data: print("DEBUG: Nenhum dado JSON."); return jsonify({"msg": "Corpo JSON ausente"}), 400
    username = data.get('username'); password = data.get('password')
    print(f"DEBUG: Tentando login: '{username}'") 
    if not username or not password: print("DEBUG: Username/password ausentes."); return jsonify({"msg": "Usuário/senha obrigatórios"}), 400
    user = User.query.filter((User.username == username) | (User.email == username)).first() 
    if user:
        print(f"DEBUG: Usuário encontrado: {user.username}")
        if user.check_password(password):
            access_token = create_access_token(identity=str(user.id)) 
            print(f"DEBUG: Login OK ID:{user.id}. Token:{access_token}")
            return jsonify(access_token=access_token)
        else: print(f"DEBUG: Senha incorreta para: '{username}'")
    else: print(f"DEBUG: Usuário não encontrado: '{username}'")
    return jsonify({"msg": "Usuário ou senha inválidos"}), 401

@app.route('/auth/me', methods=['GET'])
@jwt_required()
def protected():
    current_user_id_str = get_jwt_identity(); uid = int(current_user_id_str)
    user = User.query.get(uid)
    if not user: return jsonify({"msg":"Usuário não encontrado"}),404
    profile = UserProfile.query.filter_by(user_id=uid).first()
    profile_data = {"profile_complete":False, "nome_display": user.username, "gender":None, "communication_style":None } 
    if profile:
        for key_model in PROFILE_QUESTIONS_ORDER: # Garante que todos os campos do modelo são retornados
            profile_data[key_model] = getattr(profile, key_model, None)
        profile_data["profile_complete"] = profile.profile_complete
    return jsonify(logged_in_as=user.username,email=user.email,id=user.id,profile=profile_data),200

# --- Lógica de Matchmaking ---
PESO_JOGO_PRINCIPAL_IGUAL = 10; PESO_NIVEL_HABILIDADE_COMPATIVEL = 3; PESO_ESTILO_JOGO_IGUAL = 3
PESO_DISPONIBILIDADE_SIMILAR = 2; PESO_GENERO_COMPATIVEL = 1; PESO_COMUNICACAO_COMPATIVEL = 2
PESO_AVALIACAO_MEDIA = 4; MAX_RATING_BOOST = PESO_AVALIACAO_MEDIA
MAPA_NIVEIS = { "iniciante": 1, "casual": 2, "intermediário": 3, "avançado": 4, "competitivo/pro": 5, "novo": 1, "sou novo": 1, "ainda aprendendo": 1, "jogo por diversão": 2, "mediano":3, "comecei agora":1, "explorar": 0, "focado em diversão/casual": 0, "competitivo/subir de ranking": 0, "completar missões/história": 0, "socializar": 0, "não especificado": 0, "n/a": 0 }
MAPA_COMUNICACAO = { 'no silêncio (foco total)': 1, 'só o necessário (calls estratégicas)': 2, 'conversa casual e social': 3, 'vale tudo (cantar, zoar, resenha!)': 4, 'depende do momento/jogo': 3, 'com música e zoeira':4, 'não especificado': 0, "n/a": 0 }
def calcular_score_nivel(n1,n2):n1n=str(n1).lower().strip();n2n=str(n2).lower().strip();v1=MAPA_NIVEIS.get(n1n,0);v2=MAPA_NIVEIS.get(n2n,0);d=abs(v1-v2);return PESO_NIVEL_HABILIDADE_COMPATIVEL if d==0 else(PESO_NIVEL_HABILIDADE_COMPATIVEL*0.6 if d==1 else 0)if v1!=0 and v2!=0 else 0
def calcular_score_disponibilidade(d1,d2):d1l=str(d1).lower().strip();d2l=str(d2).lower().strip();ign={'de','a','o','e','para','com','em','no','na','durante','só','bem','as','os','todas','todos'};k1={w[:-1]if w.endswith('s')and len(w)>1 else w for w in set(d1l.replace(","," ").replace("/"," ").split())-ign};k2={w[:-1]if w.endswith('s')and len(w)>1 else w for w in set(d2l.replace(","," ").replace("/"," ").split())-ign};return PESO_DISPONIBILIDADE_SIMILAR if k1.intersection(k2)or d1l==d2l else 0 if d1l and d2l and d1l not in["n/e","n/a","não especificado"]and d2l not in["n/e","n/a","não especificado"]else 0
def calcular_score_genero(g1_s,g2_s):g1=str(g1_s).lower().strip();g2=str(g2_s).lower().strip();return PESO_GENERO_COMPATIVEL*0.2 if g1 in["n/e","prefiro não dizer","n/a","não especificado"]or g2 in["n/e","prefiro não dizer","n/a","não especificado"]else(PESO_GENERO_COMPATIVEL if g1==g2 else 0)
def calcular_score_estilo_comunicacao(c1_s,c2_s):c1n=str(c1_s).lower().strip();c2n=str(c2_s).lower().strip();v1=MAPA_COMUNICACAO.get(c1n,0);v2=MAPA_COMUNICACAO.get(c2n,0);d=abs(v1-v2);return PESO_COMUNICACAO_COMPATIVEL if d==0 else(PESO_COMUNICACAO_COMPATIVEL*0.5 if(v1>=3 and v2>=3)or(v1<=2 and v2<=2)else 0)if v1!=0 and v2!=0 else 0
def encontrar_matches_para_um_viewer(vp_dict, outros_list):
    if not vp_dict or not outros_list: return []
    kn,kg,kl,ke,kd,ki,kgen,kcom = 'nome_display','jogo_principal','nivel_de_habilidade','estilo_jogo','disponibilidade','user_id','gender','communication_style'
    matches = []; nv = vp_dict.get(kn, "Viewer"); v_jg = str(vp_dict.get(kg, '')).lower().strip()
    for pmp in outros_list:
        if vp_dict.get(ki) == pmp.get(ki): continue
        npm = pmp.get(kn, "Match"); p_uid = pmp.get(ki); st = 0.0; dr = [] # Score como float
        p_jg = str(pmp.get(kg, '')).lower().strip()
        if v_jg and p_jg and v_jg == p_jg: st += PESO_JOGO_PRINCIPAL_IGUAL; dr.append(f"Mesmo jogo ({p_jg})")
        else: continue
        sn=calcular_score_nivel(vp_dict.get(kl),pmp.get(kl));_=(st:=st+sn,dr.append("Nível compatível"))if sn>0 else 0
        ev=str(vp_dict.get(ke,'')).lower().strip();ep=str(pmp.get(ke,'')).lower().strip();_=(st:=st+PESO_ESTILO_JOGO_IGUAL,dr.append("Mesmo estilo"))if ev and ep and ev==ep else 0
        sd=calcular_score_disponibilidade(vp_dict.get(kd),pmp.get(kd));_=(st:=st+sd,dr.append("Disponibilidade similar"))if sd>0 else 0
        sgen=calcular_score_genero(vp_dict.get(kgen,""),pmp.get(kgen,""));_=(st:=st+sgen,dr.append("Gênero"))if sgen>0 else 0 # Adicionado "" como default
        scom=calcular_score_estilo_comunicacao(vp_dict.get(kcom,""),pmp.get(kcom,""));_=(st:=st+scom,dr.append("Comunicação compatível"))if scom>0 else 0
        if p_uid:
            avg_r_q = db.session.query(func.avg(MatchRating.rating)).filter_by(rated_user_id=p_uid)
            if v_jg: avg_r_q = avg_r_q.filter(func.lower(MatchRating.game_played) == v_jg)
            avg_r = avg_r_q.scalar()
            if avg_r is not None and avg_r > 0: r_b = (float(avg_r)/5.0)*MAX_RATING_BOOST; st+=r_b; dr.append(f"Bem avaliado(⭐{avg_r:.1f},+{r_b:.1f})")
        if st>0: matches.append({"user_id":p_uid,"nome":npm,"jogo":p_jg,"score":round(st,1),"razoes":", ".join(dr)if dr else "Compatibilidade!","initial":npm[0].upper()if npm and len(npm)>0 else "?"})
    matches.sort(key=lambda x:x["score"],reverse=True); return matches

# --- Endpoints de Ação de Match, Matches Mútuos, Rate Player, Send Message ---
@app.route('/api/action/match', methods=['POST'])
@jwt_required()
def action_match(): # ... (Expandido para clareza) ...
    current_user_id_str = get_jwt_identity(); current_user_id = int(current_user_id_str); data = request.json; liked_user_id_from_req = data.get('liked_user_id');
    if liked_user_id_from_req is None: return jsonify({"msg": "ID do usuário curtido obrigatório."}), 400
    try: liked_user_id = int(liked_user_id_from_req)
    except ValueError: return jsonify({"msg": "ID do usuário curtido inválido."}), 400
    if current_user_id == liked_user_id: return jsonify({"msg": "Não pode dar match consigo mesmo."}), 400
    existing_like = Like.query.filter_by(liker_user_id=current_user_id, liked_user_id=liked_user_id).first()
    if not existing_like: new_like = Like(liker_user_id=current_user_id, liked_user_id=liked_user_id); db.session.add(new_like); db.session.commit(); print(f"DEBUG: User {current_user_id} curtiu user {liked_user_id}")
    else: print(f"DEBUG: User {current_user_id} já curtiu user {liked_user_id}")
    mutual_match = Like.query.filter_by(liker_user_id=liked_user_id, liked_user_id=current_user_id).first()
    if mutual_match: print(f"DEBUG: MATCH MÚTUO! {current_user_id} e {liked_user_id}!"); lup = UserProfile.query.filter_by(user_id=liked_user_id).first(); return jsonify({"msg": "É um Match Mútuo!", "mutual_match": True, "matched_with": {"user_id": liked_user_id, "nome_display": lup.nome_display if lup else "Jogador"}}), 200
    return jsonify({"msg": "Like registrado!", "mutual_match": False}), 200

@app.route('/api/get_mutual_matches', methods=['GET'])
@jwt_required()
def get_mutual_matches(): # ... (Expandido para clareza) ...
    current_user_id_str = get_jwt_identity(); current_user_id = int(current_user_id_str)
    likes_given = Like.query.filter_by(liker_user_id=current_user_id).all(); liked_ids = {like.liked_user_id for like in likes_given}
    mutual_matches_profiles = []
    if liked_ids:
        likes_received = Like.query.filter(Like.liked_user_id == current_user_id, Like.liker_user_id.in_(liked_ids)).all()
        for like_obj in likes_received: 
            mup = UserProfile.query.filter_by(user_id=like_obj.liker_user_id).first()
            if mup: mutual_matches_profiles.append({"user_id":mup.user_id,"nome_display":mup.nome_display,"jogo_principal":mup.jogo_principal})
    return jsonify({"mutual_matches":mutual_matches_profiles}),200

@app.route('/api/rate_player', methods=['POST'])
@jwt_required()
def rate_player_endpoint(): # ... (Expandido para clareza) ...
    rater_id = int(get_jwt_identity()); data = request.json
    rated_user_id = data.get('rated_user_id'); rating_value = data.get('rating'); game_played = data.get('game_played')
    if rated_user_id is None or rating_value is None: return jsonify({"msg": "rated_user_id e rating obrigatórios."}), 400
    try: rated_user_id = int(rated_user_id); rating_value = int(rating_value); assert 1 <= rating_value <= 5, "Rating entre 1 e 5."
    except (ValueError, AssertionError) as e: return jsonify({"msg": f"Dados inválidos: {e}"}), 400
    if rater_id == rated_user_id: return jsonify({"msg": "Não pode se auto-avaliar."}), 400
    if not User.query.get(rated_user_id): return jsonify({"msg": "Usuário avaliado não encontrado."}), 404
    existing_rating = MatchRating.query.filter_by(rater_user_id=rater_id, rated_user_id=rated_user_id, game_played=game_played).first()
    if existing_rating: existing_rating.rating = rating_value; existing_rating.timestamp = datetime.utcnow(); msg = "Avaliação atualizada!"
    else: new_rating = MatchRating(rater_user_id=rater_id,rated_user_id=rated_user_id,rating=rating_value,game_played=game_played); db.session.add(new_rating); msg = "Avaliação registrada!"
    try: db.session.commit(); return jsonify({"msg": msg}), 200
    except Exception as e: db.session.rollback(); print(f"Erro salvar avaliação: {e}"); return jsonify({"msg": "Erro ao salvar avaliação."}), 500

@app.route('/api/send_message', methods=['POST'])
@jwt_required()
def send_message_endpoint(): # ... (Expandido para clareza) ...
    sender_id = int(get_jwt_identity()); data = request.json
    receiver_id_req = data.get('receiver_user_id'); content = data.get('content')
    if not receiver_id_req or not content: return jsonify({"msg": "Faltam dados"}),400
    try: receiver_id = int(receiver_id_req)
    except ValueError: return jsonify({"msg":"ID do destinatário inválido."}), 400
    if sender_id==receiver_id: return jsonify({"msg":"Não pode enviar msg para si"}),400
    l1=Like.query.filter_by(liker_user_id=sender_id,liked_user_id=receiver_id).first()
    l2=Like.query.filter_by(liker_user_id=receiver_id,liked_user_id=sender_id).first()
    if not(l1 and l2): return jsonify({"msg":"Apenas matches mútuos podem trocar msgs."}),403
    print(f"DEBUG: Msg de {sender_id} para {receiver_id}: '{content}'")
    return jsonify({"msg":"Msg enviada (simulado)!","sent_message":content}),200

# --- Endpoint da API de Matchmaking ---
@app.route('/api/get_match', methods=['GET'])
@jwt_required()
def get_match_endpoint_authenticated():
    current_user_id_str = get_jwt_identity(); uid=int(current_user_id_str)
    vp_db=UserProfile.query.filter_by(user_id=uid).first()
    if not vp_db or not vp_db.profile_complete:return jsonify({"mensagem":"Complete seu perfil gamer no chatbot!"}),403
    vpd={"user_id":vp_db.user_id,"nome_display":vp_db.nome_display,"jogo_principal":vp_db.jogo_principal, "nivel_de_habilidade":vp_db.nivel_de_habilidade,"estilo_jogo":vp_db.estilo_jogo, "disponibilidade":vp_db.disponibilidade, "gender": vp_db.gender, "communication_style": vp_db.communication_style}
    op_db=UserProfile.query.filter(UserProfile.user_id!=uid,UserProfile.profile_complete==True).all()
    ojl=[{"user_id":p.user_id,"nome_display":p.nome_display,"jogo_principal":p.jogo_principal, "nivel_de_habilidade":p.nivel_de_habilidade,"estilo_jogo":p.estilo_jogo, "disponibilidade":p.disponibilidade, "gender": p.gender, "communication_style": p.communication_style} for p in op_db]
    if not ojl:return jsonify({"matches":[],"mensagem":"END_OF_MATCHES: Não há outros jogadores."}),200
    mpv=encontrar_matches_para_um_viewer(vpd,ojl)
    if not mpv:return jsonify({"matches":[],"mensagem":f"END_OF_MATCHES: Nenhum match para {vpd.get('nome_display')}."}),200
    return jsonify({"matches":mpv[:3],"mensagem":"Matches encontrados!"})

# --- Inicialização ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    inicializar_servicos_google()
    if model_gemini is None: print("*"*50 + "\nAVISO: Modelo Gemini não carregado.\n" + "*"*50)
    print("Servidor Flask iniciado. Acesse o front-end (index.html) no seu navegador.")
    app.run(debug=True, host='0.0.0.0', port=5000)
