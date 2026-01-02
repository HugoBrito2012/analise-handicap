import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os

# Configuração da Página
st.set_page_config(page_title="Sniper HA - Backtest", layout="wide")

# ==============================================================================
# 1. CARREGAMENTO DE DADOS (CACHEADO)
# ==============================================================================
@st.cache_data
def load_data():
    # Nome do arquivo CSV que você vai subir no GitHub
    csv_file = 'MEGA_BASE_HA_COMPLETA.csv'
    
    if os.path.exists(csv_file):
        try:
            # Lê o CSV
            df = pd.read_csv(csv_file)
            
            # Converte colunas numéricas para garantir cálculos
            cols_num = ['HG', 'AG', 'HA_Line', 'HA_Odd_H', 'HA_Odd_A', 'Odd_H', 'Odd_A']
            for c in cols_num:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            return df
        except Exception as e:
            st.error(f"Erro ao ler o arquivo CSV: {e}")
            return None
    else:
        return None

# ==============================================================================
# 2. FUNÇÃO DE CÁLCULO DE LUCRO (CORE)
# ==============================================================================
def calculate_pl(row, side, line_selected):
    # Garante que temos os dados necessários na linha
    if pd.isna(row['HA_Line']) or pd.isna(row['HA_Odd_H']) or pd.isna(row['HA_Odd_A']):
        return None

    hg, ag = row['HG'], row['AG']
    
    # Lógica: O banco de dados (HA_Line) é sempre referente ao Mandante (Home).
    
    if side == 'Mandante':
        odd = row['HA_Odd_H']
        # Se aposto no mandante, a linha é a própria linha do banco
        diff = hg - ag + line_selected 
    else: # Visitante
        odd = row['HA_Odd_A']
        # Se aposto no visitante, inverto o sinal da linha
        # Ex: Se escolhi Visitante +0.5, a conta é (AG - HG) - (-0.5)
        diff = (ag - hg) - line_selected 

    stake = 1.0
    
    # Regras do Handicap Asiático
    if diff > 0.25: return (odd - 1) * stake       # Green
    elif diff < -0.25: return -stake               # Red
    elif abs(diff) < 0.01: return 0.0              # Void
    elif diff > 0: return ((odd - 1) * stake) / 2  # Half-Win
    else: return -stake / 2                        # Half-Loss

# ==============================================================================
# 3. INTERFACE DO APLICATIVO
# ==============================================================================
st.title("🎯 Sniper HA - Validador de Estratégias")
st.markdown("---")

# Carregar a base
df = load_data()

if df is None:
    st.error("⚠️ Arquivo 'MEGA_BASE_HA_COMPLETA.csv' não encontrado.")
    st.info("Certifique-se de fazer o upload do arquivo CSV para o repositório do GitHub junto com este script.")
    st.stop()

# --- SIDEBAR (CONFIGURAÇÕES) ---
st.sidebar.header("🛠️ Configuração")

# 1. Filtro de Competição
if 'Competicao' in df.columns:
    ligas = sorted(df['Competicao'].unique().astype(str))
    liga_sel = st.sidebar.selectbox("Selecione a Competição:", ligas)
    
    # Filtra o DataFrame inicial
    df_liga = df[df['Competicao'] == liga_sel].copy()
else:
    st.error("A coluna 'Competicao' não existe no arquivo.")
    st.stop()

# 2. Filtro de Estratégia (Mandante/Visitante)
lado_sel = st.sidebar.radio("Sua aposta é no:", ['Mandante', 'Visitante'])

# 3. Filtro de Linha de Handicap
# Mostra apenas as linhas que existem para aquela liga
available_lines = sorted(df_liga['HA_Line'].dropna().unique())

if lado_sel == 'Visitante':
    # Inverte visualmente para o usuário (Ex: Home -0.5 vira Visitante +0.5)
    display_lines = sorted([-x for x in available_lines])
else:
    display_lines = available_lines

if not display_lines:
    st.warning("Não há linhas de Handicap disponíveis para esta competição.")
    st.stop()

# Seleção da linha (Tenta focar no 0.0 ou -0.5 como padrão)
default_idx = 0
if -0.5 in display_lines: default_idx = display_lines.index(-0.5)
elif 0.0 in display_lines: default_idx = display_lines.index(0.0)

linha_sel = st.sidebar.selectbox("Escolha a Linha de Handicap:", display_lines, index=default_idx)

# ==============================================================================
# 4. PROCESSAMENTO E RESULTADOS
# ==============================================================================

# Filtra no Banco de Dados a linha correta
# Se escolhi Mandante -0.5, busco HA_Line == -0.5
# Se escolhi Visitante +0.5, busco HA_Line == -0.5 (pois Home -0.5 = Away +0.5)
if lado_sel == 'Mandante':
    db_line_target = linha_sel
    odd_col = 'HA_Odd_H'
else:
    db_line_target = linha_sel * -1
    odd_col = 'HA_Odd_A'

df_filtrado = df_liga[df_liga['HA_Line'] == db_line_target].copy()

if df_filtrado.empty:
    st.warning(f"⚠️ Não foram encontrados jogos com a linha {linha_sel} na base de dados para {liga_sel}.")
else:
    # Calcula o P/L
    df_filtrado['PL'] = df_filtrado.apply(lambda row: calculate_pl(row, lado_sel, linha_sel), axis=1)
    
    # Remove jogos sem resultado (ex: adiados ou sem odd)
    df_filtrado = df_filtrado.dropna(subset=['PL'])
    
    # Ordena por data
    if 'Date' in df_filtrado.columns:
        df_filtrado['Date'] = pd.to_datetime(df_filtrado['Date'])
        df_filtrado = df_filtrado.sort_values('Date')
    
    # Acumulado
    df_filtrado['Lucro_Acumulado'] = df_filtrado['PL'].cumsum()

    # --- DASHBOARD ---
    
    # Métricas Topo
    total_jogos = len(df_filtrado)
    lucro_total = df_filtrado['PL'].sum()
    roi = (lucro_total / total_jogos) * 100
    odd_media = df_filtrado[odd_col].mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Volume", f"{total_jogos} jogos")
    c2.metric("Lucro Total", f"{lucro_total:.2f} u", delta_color="normal")
    c3.metric("ROI", f"{roi:.2f}%", delta=f"{roi:.2f}%")
    c4.metric("Odd Média", f"{odd_media:.2f}")

    # Gráfico e Tabela
    st.subheader("📈 Evolução e Consistência")
    
    tab1, tab2 = st.tabs(["Gráfico de Lucro", "Tabela por Temporada"])
    
    with tab1:
        fig = px.line(df_filtrado, x='Date', y='Lucro_Acumulado', 
                      title=f"Curva de Performance: {liga_sel} ({lado_sel} {linha_sel})")
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        if 'Temporada' in df_filtrado.columns:
            resumo = df_filtrado.groupby('Temporada').agg(
                Jogos=('PL', 'count'),
                Lucro=('PL', 'sum'),
                ROI=('PL', 'mean')
            ).reset_index()
            
            resumo['ROI'] = (resumo['ROI'] * 100).round(2).astype(str) + '%'
            resumo['Lucro'] = resumo['Lucro'].round(2)
            st.dataframe(resumo, use_container_width=True, hide_index=True)
        else:
            st.info("Coluna 'Temporada' não encontrada para agrupamento.")
