# backend/app.py

from flask import Flask, jsonify, request
from flask_cors import CORS
# import gspread # Mantido caso queira reativar algo com Sheets no futuro
# from google.oauth2.service_account import Credentials as ServiceAccountCredentials # Mesma observação acima
import os
import random
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager
from dotenv import load_dotenv
from datetime import datetime

# --- Configurações da Aplicação ---
app = Flask(__name__)
load_dotenv() 
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# --- Configurações do Banco de Dados ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tinder_gamer.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-super-secret-key-gg-chatbot-v10') # Mude no .env

# --- Configurações do Gemini ---
model_gemini = None

db = SQLAlchemy(app)
jwt = JWTManager(app)

# --- Modelos de Dados (SQLAlchemy) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile = db.relationship('UserProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    likes_given = db.relationship('Like', foreign_keys='Like.liker_user_id', backref='liker', lazy='dynamic', cascade="all, delete-orphan")
    likes_received = db.relationship('Like', foreign_keys='Like.liked_user_id', backref='liked', lazy='dynamic', cascade="all, delete-orphan")

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

# --- Lógica do Chatbot de Perfil ---
user_chatbot_state = {} 
PROFILE_QUESTIONS_ORDER = ['nome_display', 'jogo_principal', 'nivel_de_habilidade', 'estilo_jogo', 'disponibilidade', 'gender', 'communication_style']
PROFILE_GEMINI_EXTRACTION_FIELDS = {
    'nome_display': "Nome do jogador ou apelido do jogador", 'jogo_principal': "Principal jogo de interesse do jogador",
    'nivel_de_habilidade': "Nível de habilidade do jogador no jogo principal", 'estilo_jogo': "Estilo de jogo preferido do jogador",
    'disponibilidade': "Disponibilidade geral do jogador para jogar", 'gender': "Identidade de gênero do jogador",
    'communication_style': "Preferência de comunicação do jogador durante o jogo (ex: no silêncio, conversa, zoeira)"
}
PROFILE_GEMINI_CATEGORIES = {
    'nivel_de_habilidade': ['Iniciante', 'Intermediário', 'Avançado', 'Competitivo/Pro', 'Ainda aprendendo', 'Jogo por diversão', 'Mediano'],
    'estilo_jogo': ['Focado em Diversão', 'Competitivo/Subir de Ranking', 'Completar Missões/História', 'Explorar Mundos', 'Socializar com amigos', 'Variado/Depende do humor'],
    'gender': ['Mulher', 'Homem', 'Não-binário', 'Gênero fluido', 'Agênero', 'Prefiro não dizer', 'Outro'],
    'communication_style': ['No silêncio (foco total)', 'Só o necessário (calls estratégicas)', 'Conversa casual e social', 'Vale tudo (cantar, zoar, resenha!)', 'Depende do momento/jogo']
}
BASE_QUESTION_IDEAS = {
    'greeting': "Olá! Sou o GG, seu guia para montar o perfil gamer perfeito e encontrar seu squad ideal! Para começar,",
    'nome_display': "como você gostaria de ser chamado(a) aqui na plataforma?", 'jogo_principal': "qual é o principal jogo que você mais curte no momento e quer encontrar parceiros?",
    'nivel_de_habilidade': "legal! E no {jogo_principal}, como você descreveria seu nível de habilidade?",
    'estilo_jogo': "entendi. E qual seu estilo de jogo preferido no {jogo_principal}? Mais casual, competitivo, ou outro?",
    'disponibilidade': "show! E quando você geralmente tem aquele tempo livre para as gameplays?", 'gender': "para te conhecer um pouco melhor, como você se identifica em termos de gênero?",
    'communication_style': "e durante a partida, como você prefere a comunicação? Mais focado, resenha, ou algo assim?",
    'final': "Perfeito, {nome_display}! Seu perfil gamer está configurado e pronto para a ação! GG! Agora pode buscar por matches."
}
BOT_PERSONALITY_PROMPT = "Você é GG, um assistente amigável e entusiasta por games, aqui para ajudar jogadores a criar seus perfis. Seu tom é natural, conversacional e prestativo. Você pode usar uma linguagem levemente informal, mas evite gírias excessivas ou forçadas. O seu objetivo é fazer com que o usuário se sinta confortável para compartilhar suas preferências. Mantenha as perguntas e comentários curtos e diretos."

def generate_bot_question(current_field_to_ask, previous_user_response, collected_data, is_first_question):
    if not model_gemini: 
        fallback_question_idea = BASE_QUESTION_IDEAS.get(current_field_to_ask, "Pode me falar mais sobre isso?")
        if is_first_question: return f"{BASE_QUESTION_IDEAS['greeting']} {fallback_question_idea.format(**collected_data)}"
        return fallback_question_idea.format(**collected_data)
    prompt_parts = [BOT_PERSONALITY_PROMPT]
    if is_first_question:
        prompt_parts.append(f"{BASE_QUESTION_IDEAS['greeting']} sua primeira pergunta é para saber: {PROFILE_GEMINI_EXTRACTION_FIELDS[current_field_to_ask]}. Pergunta:")
    else:
        if previous_user_response: prompt_parts.append(f"O usuário acabou de responder: \"{previous_user_response}\". Faça um breve comentário de reconhecimento (uma frase curta e natural, como 'Entendi!', 'Legal!', 'Show!') se apropriado, e então,")
        context_str = "Considerando o que já sabemos"
        if 'nome_display' in collected_data: context_str += f" (o nome é {collected_data['nome_display']})"
        if 'jogo_principal' in collected_data and current_field_to_ask != 'jogo_principal': context_str += f" e que joga {collected_data['jogo_principal']}"
        base_idea_for_question = BASE_QUESTION_IDEAS[current_field_to_ask].format(**collected_data)
        prompt_parts.append(f"{context_str}, formule a próxima pergunta para obter a informação sobre: '{PROFILE_GEMINI_EXTRACTION_FIELDS[current_field_to_ask]}'.")
        prompt_parts.append(f"Use a seguinte ideia base para a pergunta, mas adapte para seu estilo e evite ser repetitivo: \"{base_idea_for_question}\".")
        prompt_parts.append("Mantenha a pergunta (e o comentário, se houver) curta e direta ao ponto.")
        prompt_parts.append("Pergunta Gerada (incluindo breve comentário, se houver):")
    full_prompt = "\n".join(prompt_parts)
    try:
        response = model_gemini.generate_content(full_prompt); question = response.text.strip()
        if question.lower().startswith("pergunta gerada:"): question = question.split(":",1)[-1].strip()
        return question if question else BASE_QUESTION_IDEAS[current_field_to_ask].format(**collected_data)
    except Exception as e: print(f"Erro ao gerar pergunta Gemini para '{current_field_to_ask}': {e}"); return BASE_QUESTION_IDEAS[current_field_to_ask].format(**collected_data)

def extrair_info_chatbot_com_gemini(texto_usuario, campo_desejado):
    if not model_gemini: print("AVISO: Modelo Gemini não carregado para extração."); return texto_usuario 
    categorias = PROFILE_GEMINI_CATEGORIES.get(campo_desejado); prompt_field_description = PROFILE_GEMINI_EXTRACTION_FIELDS.get(campo_desejado, campo_desejado)
    prompt = f"Do texto do usuário: \"{texto_usuario}\", extraia APENAS a informação correspondente a '{prompt_field_description}'."
    if categorias: prompt += f"\nClassifique o resultado em UMA das seguintes categorias: {categorias}. Se a informação não se encaixar claramente ou não for fornecida, retorne 'Não especificado'."
    else: prompt += f"\nRetorne a informação de forma concisa. Se não for fornecida ou não for clara, retorne 'Não especificado'."
    prompt += f"\n{prompt_field_description}:"
    try:
        response = model_gemini.generate_content(prompt); info_extraida = response.text.strip()
        if ":" in info_extraida: info_extraida = info_extraida.split(":", 1)[-1].strip()
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
    if question_idx > 0 and user_message: 
        prev_question_field_idx = question_idx -1
        if prev_question_field_idx < len(PROFILE_QUESTIONS_ORDER):
            prev_question_field = PROFILE_QUESTIONS_ORDER[prev_question_field_idx]
            extracted_info = extrair_info_chatbot_com_gemini(user_message, prev_question_field)
            state['collected_data'][prev_question_field] = extracted_info
            print(f"User {current_user_id} - Campo '{prev_question_field}': Resp '{user_message}', Extr '{extracted_info}'")
    state['last_user_response'] = user_message
    if question_idx < len(PROFILE_QUESTIONS_ORDER): 
        current_field_to_ask = PROFILE_QUESTIONS_ORDER[question_idx]
        is_first = (question_idx == 0 and not user_message)
        previous_response = state['last_user_response'] if not is_first and question_idx > 0 else None
        bot_question = generate_bot_question(current_field_to_ask, previous_response, state['collected_data'], is_first or question_idx == 0)
        state['current_question_idx'] += 1
        return jsonify({"bot_response": bot_question, "profile_complete": False})
    else:
        user_profile = UserProfile.query.filter_by(user_id=current_user_id).first()
        if not user_profile: user_profile = UserProfile(user_id=current_user_id); db.session.add(user_profile)
        for field in PROFILE_QUESTIONS_ORDER: user_profile.__setattr__(field, state['collected_data'].get(field, getattr(user_profile, field, None)))
        user_profile.profile_complete = True
        try: 
            db.session.commit(); nome_final = state['collected_data'].get('nome_display', 'Jogador(a)')
            final_message = BASE_QUESTION_IDEAS['final'].format(nome_display=nome_final)
            if current_user_id in user_chatbot_state: del user_chatbot_state[current_user_id] 
            return jsonify({"bot_response": final_message, "profile_complete": True, "profile_data": state['collected_data']})
        except Exception as e: 
            db.session.rollback(); print(f"Erro ao salvar perfil user {current_user_id}: {e}")
            return jsonify({"bot_response": "Ops! Problema ao salvar.", "profile_complete": False, "error": str(e)}), 500

# --- Endpoints de Autenticação (Reescritos para Clareza) ---
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({"msg": "Faltam dados (username, email ou password)"}), 400
    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return jsonify({"msg": "Usuário ou email já cadastrado"}), 409
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"msg": "Usuário cadastrado com sucesso!"}), 201

@app.route('/auth/login', methods=['POST'])
def login():
    print("DEBUG: Rota /auth/login acessada.") 
    try:
        data = request.json
        print(f"DEBUG: Dados recebidos no login: {data}") 
        if not data:
            print("DEBUG: Nenhum dado JSON recebido no corpo da requisição.")
            return jsonify({"msg": "Corpo da requisição JSON ausente ou inválido"}), 400
        username = data.get('username')
        password = data.get('password')
        print(f"DEBUG: Tentando login com username/email: '{username}'") 
        if not username or not password:
            print("DEBUG: Username ou password ausentes nos dados recebidos.")
            return jsonify({"msg": "Nome de usuário e senha são obrigatórios"}), 400
        user = User.query.filter_by(username=username).first() 
        if not user: 
            user = User.query.filter_by(email=username).first() 
            if user: print(f"DEBUG: Usuário encontrado pelo email: {username}")
        if user and user.check_password(password):
            access_token = create_access_token(identity=str(user.id)) 
            print(f"DEBUG: Login OK para ID: {user.id}. Token gerado: {access_token}")
            return jsonify(access_token=access_token)
        print(f"DEBUG: Falha no login para: '{username}' - Usuário não encontrado ou senha incorreta.") 
        return jsonify({"msg": "Usuário ou senha inválidos"}), 401
    except Exception as e:
        print(f"DEBUG: Erro inesperado na rota /auth/login: {e}")
        import traceback
        print(traceback.format_exc()) 
        return jsonify({"msg": "Erro interno no servidor ao processar o login"}), 500

@app.route('/auth/me', methods=['GET'])
@jwt_required()
def protected():
    current_user_id_str = get_jwt_identity()
    try: current_user_id = int(current_user_id_str)
    except ValueError: return jsonify({"msg": "Formato de ID de usuário inválido no token"}), 422
    user = User.query.get(current_user_id)
    if not user: return jsonify({"msg": "Usuário não encontrado com o ID do token"}), 404
    profile = UserProfile.query.filter_by(user_id=current_user_id).first()
    profile_data = {"profile_complete":False, "nome_display": user.username, "gender":None, "communication_style":None } 
    if profile: 
        profile_data.update({
            "nome_display": profile.nome_display, "jogo_principal": profile.jogo_principal, 
            "nivel_de_habilidade": profile.nivel_de_habilidade, "estilo_jogo": profile.estilo_jogo, 
            "disponibilidade": profile.disponibilidade, "gender": profile.gender, 
            "communication_style": profile.communication_style, "profile_complete": profile.profile_complete
        })
    return jsonify(logged_in_as=user.username,email=user.email,id=user.id,profile=profile_data),200

# --- Lógica de Matchmaking ---
PESO_JOGO_PRINCIPAL_IGUAL = 10; PESO_NIVEL_HABILIDADE_COMPATIVEL = 3; PESO_ESTILO_JOGO_IGUAL = 3; PESO_DISPONIBILIDADE_SIMILAR = 2; PESO_GENERO_COMPATIVEL = 1; PESO_COMUNICACAO_COMPATIVEL = 2
MAPA_NIVEIS = { "iniciante": 1, "casual": 2, "intermediário": 3, "avançado": 4, "competitivo/pro": 5, "novo": 1, "sou novo": 1, "ainda aprendendo": 1, "jogo por diversão": 2, "mediano":3, "explorar": 0, "focado em diversão/casual": 0, "competitivo/subir de ranking": 0, "completar missões/história": 0, "socializar": 0, "não especificado": 0, "n/a": 0 }
MAPA_COMUNICACAO = { 'no silêncio (foco total)': 1, 'só o necessário (calls estratégicas)': 2, 'conversa casual e social': 3, 'vale tudo (cantar, zoar, resenha!)': 4, 'depende do momento/jogo': 3, 'não especificado': 0, "n/a": 0 }
def calcular_score_nivel(n1, n2): n1n=str(n1).lower().strip(); n2n=str(n2).lower().strip(); v1=MAPA_NIVEIS.get(n1n,0); v2=MAPA_NIVEIS.get(n2n,0); d=abs(v1-v2); return PESO_NIVEL_HABILIDADE_COMPATIVEL if d==0 else (PESO_NIVEL_HABILIDADE_COMPATIVEL*0.6 if d==1 else 0) if v1!=0 and v2!=0 else 0
def calcular_score_disponibilidade(d1,d2): d1l=str(d1).lower().strip();d2l=str(d2).lower().strip();ign={'de','a','o','e','para','com','em','no','na','durante','só','bem','as','os','todas','todos'};k1={w[:-1]if w.endswith('s')and len(w)>1 else w for w in set(d1l.replace(","," ").replace("/"," ").split())-ign};k2={w[:-1]if w.endswith('s')and len(w)>1 else w for w in set(d2l.replace(","," ").replace("/"," ").split())-ign};return PESO_DISPONIBILIDADE_SIMILAR if k1.intersection(k2)or d1l==d2l else 0 if d1l and d2l and d1l not in["n/e","n/a", "não especificado"]and d2l not in["n/e","n/a", "não especificado"]else 0
def calcular_score_genero(g1_str, g2_str): g1=str(g1_str).lower().strip();g2=str(g2_str).lower().strip();_ = PESO_GENERO_COMPATIVEL*0.2 if g1 in ["não especificado","prefiro não dizer","n/a"] or g2 in ["não especificado","prefiro não dizer","n/a"] else (PESO_GENERO_COMPATIVEL if g1==g2 else 0); return _
def calcular_score_estilo_comunicacao(c1_str,c2_str):c1n=str(c1_str).lower().strip();c2n=str(c2_str).lower().strip();v1=MAPA_COMUNICACAO.get(c1n,0);v2=MAPA_COMUNICACAO.get(c2n,0);d=abs(v1-v2);return PESO_COMUNICACAO_COMPATIVEL if d==0 else(PESO_COMUNICACAO_COMPATIVEL*0.5 if(v1>=3 and v2>=3)or(v1<=2 and v2<=2)else 0)if v1!=0 and v2!=0 else 0

def encontrar_matches_para_um_viewer(viewer_profile_dict, todos_os_outros_jogadores_list):
    if not viewer_profile_dict or not todos_os_outros_jogadores_list: return []
    kn,kg,kl,ke,kd,ki,kgen,kcom = 'nome_display','jogo_principal','nivel_de_habilidade','estilo_jogo','disponibilidade','user_id','gender','communication_style'
    matches_para_este_viewer = []
    nome_viewer = viewer_profile_dict.get(kn, "Viewer")
    print(f"DEBUG Matchmaking: Calculando para viewer: {nome_viewer} (ID: {viewer_profile_dict.get(ki)}) com perfil: {viewer_profile_dict}")
    for p_match_profile in todos_os_outros_jogadores_list:
        if viewer_profile_dict.get(ki) == p_match_profile.get(ki): continue
        nome_p_match = p_match_profile.get(kn, "Match")
        score_total = 0; detalhes_razoes = []
        jogo_v = str(viewer_profile_dict.get(kg, '')).lower().strip(); jogo_p = str(p_match_profile.get(kg, '')).lower().strip()
        if jogo_v and jogo_p and jogo_v == jogo_p: score_total += PESO_JOGO_PRINCIPAL_IGUAL; detalhes_razoes.append(f"Mesmo jogo ({jogo_v})")
        else: continue
        score_nivel = calcular_score_nivel(viewer_profile_dict.get(kl), p_match_profile.get(kl))
        if score_nivel > 0: score_total += score_nivel; detalhes_razoes.append(f"Nível compatível")
        estilo_v = str(viewer_profile_dict.get(ke,'')).lower().strip(); estilo_p = str(p_match_profile.get(ke,'')).lower().strip()
        if estilo_v and estilo_p and estilo_v == estilo_p: score_total += PESO_ESTILO_JOGO_IGUAL; detalhes_razoes.append(f"Mesmo estilo")
        score_disp = calcular_score_disponibilidade(viewer_profile_dict.get(kd), p_match_profile.get(kd))
        if score_disp > 0: score_total += score_disp; detalhes_razoes.append(f"Disponibilidade similar")
        score_genero = calcular_score_genero(viewer_profile_dict.get(kgen), p_match_profile.get(kgen))
        if score_genero > 0: score_total += score_genero; detalhes_razoes.append(f"Gênero")
        score_comunicacao = calcular_score_estilo_comunicacao(viewer_profile_dict.get(kcom), p_match_profile.get(kcom))
        if score_comunicacao > 0: score_total += score_comunicacao; detalhes_razoes.append(f"Comunicação compatível")
        if score_total > 0:
            matches_para_este_viewer.append({
                "user_id": p_match_profile.get(ki), "nome": nome_p_match, "jogo": jogo_p, 
                "score": round(score_total, 1),
                "razoes": ", ".join(detalhes_razoes) if detalhes_razoes else "Boa compatibilidade!",
                "initial": nome_p_match[0].upper()if nome_p_match and len(nome_p_match)>0 else "?"
            })
    matches_para_este_viewer.sort(key=lambda x:x["score"],reverse=True)
    return matches_para_este_viewer

# --- Endpoints de Ação de Match e Matches Mútuos ---
@app.route('/api/action/match', methods=['POST'])
@jwt_required()
def action_match():
    current_user_id_str = get_jwt_identity(); current_user_id = int(current_user_id_str)
    data = request.json; liked_user_id_from_req = data.get('liked_user_id')
    if liked_user_id_from_req is None: return jsonify({"msg": "ID do usuário curtido obrigatório."}), 400
    try: liked_user_id = int(liked_user_id_from_req)
    except ValueError: return jsonify({"msg": "ID do usuário curtido inválido."}), 400
    if current_user_id == liked_user_id: return jsonify({"msg": "Não pode dar match consigo mesmo."}), 400
    existing_like = Like.query.filter_by(liker_user_id=current_user_id, liked_user_id=liked_user_id).first()
    if not existing_like:
        new_like = Like(liker_user_id=current_user_id, liked_user_id=liked_user_id)
        db.session.add(new_like); db.session.commit()
        print(f"DEBUG: User {current_user_id} curtiu user {liked_user_id}")
    else: print(f"DEBUG: User {current_user_id} já curtiu user {liked_user_id}")
    mutual_match = Like.query.filter_by(liker_user_id=liked_user_id, liked_user_id=current_user_id).first()
    if mutual_match:
        print(f"DEBUG: MATCH MÚTUO! {current_user_id} e {liked_user_id}!")
        lup = UserProfile.query.filter_by(user_id=liked_user_id).first()
        return jsonify({"msg": "É um Match Mútuo!", "mutual_match": True, "matched_with": {"user_id": liked_user_id, "nome_display": lup.nome_display if lup else "Jogador"}}), 200
    return jsonify({"msg": "Like registrado!", "mutual_match": False}), 200

@app.route('/api/get_mutual_matches', methods=['GET'])
@jwt_required()
def get_mutual_matches():
    current_user_id_str = get_jwt_identity(); current_user_id = int(current_user_id_str)
    likes_given = Like.query.filter_by(liker_user_id=current_user_id).all()
    liked_ids = {like.liked_user_id for like in likes_given}
    mutual_matches_profiles = []
    if liked_ids:
        likes_received = Like.query.filter(Like.liked_user_id == current_user_id, Like.liker_user_id.in_(liked_ids)).all()
        for like in likes_received:
            mup = UserProfile.query.filter_by(user_id=like.liker_user_id).first()
            if mup: mutual_matches_profiles.append({"user_id":mup.user_id,"nome_display":mup.nome_display,"jogo_principal":mup.jogo_principal})
    print(f"DEBUG: User {current_user_id} tem {len(mutual_matches_profiles)} matches mútuos.")
    return jsonify({"mutual_matches":mutual_matches_profiles}),200

@app.route('/api/send_message', methods=['POST'])
@jwt_required()
def send_message_endpoint():
    current_user_id_str = get_jwt_identity(); sender_id = int(current_user_id_str)
    data = request.json; receiver_user_id_req = data.get('receiver_user_id'); message_content = data.get('content')
    if not receiver_user_id_req or not message_content: return jsonify({"msg": "Faltam dados"}),400
    try: receiver_user_id = int(receiver_user_id_req)
    except ValueError: return jsonify({"msg":"ID do destinatário inválido."}), 400
    if sender_id==receiver_user_id: return jsonify({"msg":"Não pode enviar msg para si"}),400
    like1=Like.query.filter_by(liker_user_id=sender_id,liked_user_id=receiver_user_id).first()
    like2=Like.query.filter_by(liker_user_id=receiver_user_id,liked_user_id=sender_id).first()
    if not(like1 and like2): return jsonify({"msg":"Apenas matches mútuos podem trocar msgs."}),403
    print(f"DEBUG: Msg de {sender_id} para {receiver_user_id}: '{message_content}'")
    return jsonify({"msg":"Msg enviada (simulado)!","sent_message":message_content}),200

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
    if not ojl:return jsonify({"matches":[],"mensagem":"END_OF_MATCHES: Não há outros jogadores com perfil completo."}),200
    mpv=encontrar_matches_para_um_viewer(vpd,ojl)
    if not mpv:return jsonify({"matches":[],"mensagem":f"END_OF_MATCHES: Nenhum match compatível para {vpd.get('nome_display')}."}),200
    return jsonify({"matches":mpv[:3],"mensagem":"Matches encontrados!"})

# --- Inicialização ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    inicializar_servicos_google()
    if model_gemini is None: print("*"*50 + "\nAVISO: Modelo Gemini não carregado.\n" + "*"*50)
    print("Servidor Flask iniciado. Acesse o front-end (index.html) no seu navegador.")
    app.run(debug=True, host='0.0.0.0', port=5000)
