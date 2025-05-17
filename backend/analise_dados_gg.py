# backend/analise_dados_gg.py

import os
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from flask_sqlalchemy import SQLAlchemy # Usaremos para os modelos
from flask import Flask # Necessário para inicializar o contexto do SQLAlchemy fora do app principal


temp_app = Flask(__name__)
temp_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tinder_gamer.db' # Mesmo caminho do DB
temp_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(temp_app) # Associa o SQLAlchemy a este app temporário


class User(db.Model):
    __tablename__ = 'user' # Garante que use a tabela existente
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    # profile = db.relationship('UserProfile', backref='user', uselist=False) # Não precisamos do relationship aqui para contagens

class UserProfile(db.Model):
    __tablename__ = 'user_profile' # Garante que use a tabela existente
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
    __tablename__ = 'like'
    id = db.Column(db.Integer, primary_key=True)
    liker_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    liked_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime) # Não precisa do default aqui para análise

class MatchRating(db.Model):
    __tablename__ = 'match_rating'
    id = db.Column(db.Integer, primary_key=True)
    rater_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rated_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) 
    game_played = db.Column(db.String(100), nullable=True) 
    timestamp = db.Column(db.DateTime)


def gerar_relatorio_basico(session):
    print("--- Relatório Básico da Comunidade GG ---")

    # 1. Número total de usuários cadastrados
    total_usuarios = session.query(User).count()
    print(f"\n1. Total de Usuários Cadastrados: {total_usuarios}")

    # 2. Número de usuários com perfil completo
    perfis_completos = session.query(UserProfile).filter_by(profile_complete=True).count()
    print(f"2. Usuários com Perfil Completo: {perfis_completos}")
    if total_usuarios > 0:
        percent_completo = (perfis_completos / total_usuarios) * 100
        print(f"   ({percent_completo:.2f}% dos usuários totais)")

    # 3. Top 3 Jogos Principais mais populares
    print("\n3. Top 3 Jogos Principais Mais Populares:")
    top_jogos = session.query(
        UserProfile.jogo_principal, 
        func.count(UserProfile.jogo_principal).label('contagem')
    ).filter(UserProfile.jogo_principal != None, UserProfile.jogo_principal != "Não especificado").group_by(UserProfile.jogo_principal).order_by(func.count(UserProfile.jogo_principal).desc()).limit(3).all()
    
    if top_jogos:
        for i, (jogo, contagem) in enumerate(top_jogos):
            print(f"   {i+1}. {jogo}: {contagem} jogadores")
    else:
        print("   Nenhum jogo principal preenchido ainda.")

    # 4. Número total de "Likes" dados
    total_likes = session.query(Like).count()
    print(f"\n4. Total de 'Likes' (Aceites) Registrados: {total_likes}")

    # 5. Número de Matches Mútuos
    # Um match mútuo é quando A curte B E B curte A
    # Esta query é um pouco mais complexa, vamos simplificar contando pares
    subquery_likes = session.query(Like.liker_user_id, Like.liked_user_id).subquery()
    mutual_matches_count = session.query(Like).join(
        subquery_likes,
        (Like.liker_user_id == subquery_likes.c.liked_user_id) & \
        (Like.liked_user_id == subquery_likes.c.liker_user_id)
    ).count()
    # Cada match mútuo será contado duas vezes (A->B e B->A), então dividi por 2
    print(f"5. Número Estimado de Pares de Match Mútuo: {mutual_matches_count // 2}")


    # 6. Média de Avaliações (se houver avaliações)
    print("\n6. Avaliações de Jogadores:")
    avg_ratings = session.query(
        UserProfile.nome_display,
        func.avg(MatchRating.rating).label('media_avaliacoes'),
        func.count(MatchRating.id).label('numero_avaliacoes')
    ).select_from(MatchRating).join(UserProfile, UserProfile.user_id == MatchRating.rated_user_id).group_by(UserProfile.nome_display).order_by(func.avg(MatchRating.rating).desc()).all()

    if avg_ratings:
        print("   Média de Avaliações por Jogador Avaliado:")
        for nome, media, n_avaliacoes in avg_ratings:
            print(f"   - {nome}: {media:.2f} estrelas ({n_avaliacoes} avaliações)")
    else:
        print("   Nenhuma avaliação registrada ainda.")
    
    print("\n--- Fim do Relatório ---")


if __name__ == '__main__':
    # Cria uma sessão para interagir com o banco de dados
    # Certifique-se que o arquivo tinder_gamer.db está no mesmo diretório ou forneça o caminho correto
    engine = create_engine(temp_app.config['SQLALCHEMY_DATABASE_URI'])
    Session = sessionmaker(bind=engine)
    session = Session()

    # Para garantir que as tabelas sejam criadas se não existirem (caso rode este script antes do app.py)
    # No entanto, é melhor que o app.py seja o responsável primário pela criação.
    # with temp_app.app_context():
    #     db.create_all() # Pode comentar se o app.py já criou as tabelas

    gerar_relatorio_basico(session)

    session.close()