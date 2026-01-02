import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os
import re

# Configuração da Página
st.set_page_config(page_title="Sniper HA - Análise Corrigida", layout="wide")

# ==============================================================================
# 1. CARREGAMENTO E LIMPEZA DE DADOS
# ==============================================================================
@st.cache_data
def load_data():
    csv_file = 'MEGA_BASE_HA_COMPLETA.csv'
    
    if os.path.exists(csv_file):
        try:
            # Lê o CSV tratando tudo como string inicialmente para limpar vírgulas
            df = pd.read_csv(csv_file, dtype=str)
            
            # 1. Tratamento de Números (Vírgula para Ponto)
            cols_to_fix = ['HG', 'AG', 'HA_Line', 'HA_Odd_H', 'HA_Odd_A', 'Odd_H', 'Odd_A']
            for col in cols_to_fix:
                if col in df.columns:
                    df[col] = df[col].str.replace('"', '', regex=False)
                    df[col] = df[col].str.replace(',', '.', regex=False)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 2. Consolidação de Nomes (Agrupar Temporadas)
            if 'Competicao' in df.columns:
                def limpar_nome_liga(nome):
                    if pd.isna(nome): return "Indefinido"
                    nome = str(nome)
                    # Remove anos e sufixos de temporada para agrupar tudo
                    nome = re.sub(r'[_\s-]?20\d{2}', '', nome)
                    nome = re.sub(r'[_\s-]?\d{4}', '', nome)
                    nome = re.sub(r'\d{2}/\d{2}', '', nome)
                    nome = re.sub(r'_G\d+', '', nome)
                    nome = nome.replace('_', ' ').strip()
                    return nome

                df['Liga_Ref'] = df['Competicao'].apply(limpar_nome_liga)
            else:
                st.error("Coluna 'Competicao' não encontrada.")
                return pd.DataFrame()

            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

            return df
        except Exception as e:
            st.error(f"Erro ao processar CSV: {e}")
            return None
    else:
        return None

# ==============================================================================
# 2. CÁLCULO DE LUCRO (CORRIGIDO)
# ==============================================================================
def calculate_pl(row, side, line_selected):
    # line_selected: É a linha que O USUÁRIO escolheu. 
    # Ex: Se escolheu Visitante Favorito -1.5, line_selected é -1.5.

    if pd.isna(row['HA_Line']) or pd.isna(row['HA_Odd_H']) or pd.isna(row['HA_Odd_A']):
        return None

    hg, ag = row['HG'], row['AG']
    
    # --- FÓRMULA CORRIGIDA ---
    # A lógica é sempre: (Gols a Favor - Gols Contra) + Handicap
    
    if side == 'Mandante':
        odd = row['HA_Odd_H']
        # Apostou no Mandante: (Home - Away) + Linha
        diff = (hg - ag) + line_selected 
        
    else: # Visitante
        odd = row['HA_Odd_A']
        # Apostou no Visitante: (Away - Home) + Linha
        # Se line_selected for -1.5, a conta fica: Saldo + (-1.5) -> Saldo - 1.5. CORRETO.
        diff = (ag - hg) + line_selected 

    stake = 1.0
    
    # Regras de Payout (Verifica a diferença ajustada pelo handicap)
    if diff > 0.25: return (odd - 1) * stake       # Green Completo
    elif diff < -0.25: return -stake               # Red Completo
    elif abs(diff) < 0.01: return 0.0              # Reembolso (Void)
    elif diff > 0: return ((odd - 1) * stake) / 2  # Meio Green (0.25)
    else: return -stake / 2                        # Meio Red (-0.25)

# ==============================================================================
# 3. INTERFACE
# ==============================================================================
st.title("🎯 Sniper HA - Validador (Fórmula Corrigida)")

df = load_data()

if df is None or df.empty:
    st.warning("⚠️ Arquivo CSV não carregado.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuração")

# 1. LIGA
ligas_unicas = sorted(df['Liga_Ref'].unique())
liga_sel = st.sidebar.selectbox("Competição", ligas_unicas)
df_liga = df[df['Liga_Ref'] == liga_sel].copy()

# 2. LADO
lado_sel = st.sidebar.radio("Apostar em:", ['Mandante', 'Visitante'])

# 3. LINHA (COM MEMÓRIA)
available_lines = sorted(df_liga['HA_Line'].dropna().unique())

# Se Visitante, invertemos a exibição das linhas baseadas no Home
# Ex: Se no DB tem Home +1.5, mostramos Visitante -1.5
if lado_sel == 'Visitante':
    display_lines = sorted([-x for x in available_lines])
else:
    display_lines = available_lines

if not display_lines:
    st.warning("Sem dados.")
    st.stop()

# Persistência da escolha
last = st.session_state.get('last_line', -0.5)
try:
    idx = display_lines.index(last)
except:
    if -0.5 in display_lines: idx = display_lines.index(-0.5)
    elif 0.0 in display_lines: idx = display_lines.index(0.0)
    else: idx = 0

linha_sel = st.sidebar.selectbox("Linha de Handicap", display_lines, index=idx)
st.session_state['last_line'] = linha_sel

st.sidebar.markdown("---")
btn_rodar = st.sidebar.button("🚀 Processar", type="primary")

# ==============================================================================
# 4. EXIBIÇÃO
# ==============================================================================
if btn_rodar:
    st.session_state['run'] = True

if st.session_state.get('run'):
    
    # Traduzir a linha do Usuário para a linha do Banco de Dados
    if lado_sel == 'Mandante':
        db_target = linha_sel
        odd_col = 'HA_Odd_H'
    else:
        # Se Usuário escolheu Visitante -1.5, no DB (Home) isso é +1.5
        db_target = linha_sel * -1 
        odd_col = 'HA_Odd_A'

    # Filtra jogos
    df_f = df_liga[df_liga['HA_Line'] == db_target].copy()

    if df_f.empty:
        st.info(f"Nenhum jogo encontrado para {lado_sel} {linha_sel}.")
    else:
        # Calcula Lucro
        df_f['PL'] = df_f.apply(lambda row: calculate_pl(row, lado_sel, linha_sel), axis=1)
        df_f = df_f.dropna(subset=['PL'])

        # Ordena Data
        df_f = df_f.sort_values('Date')
        df_f['Acumulado'] = df_f['PL'].cumsum()

        # --- KPI ---
        st.markdown(f"### 📊 {liga_sel} | {lado_sel} {linha_sel}")
        
        tot_pl = df_f['PL'].sum()
        tot_games = len(df_f)
        roi = (tot_pl / tot_games) * 100 if tot_games > 0 else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Jogos", tot_games)
        c2.metric("Lucro (u)", f"{tot_pl:.2f}", delta_color="normal")
        c3.metric("ROI", f"{roi:.2f}%", delta=f"{roi:.2f}%")
        c4.metric("Odd Média", f"{df_f[odd_col].mean():.2f}")

        st.divider()

        # --- TABELA TEMPORADAS ---
        st.subheader("📅 Por Temporada")
        if 'Temporada' in df_f.columns:
            resumo = df_f.groupby('Temporada').agg(
                Jogos=('PL', 'count'),
                Lucro=('PL', 'sum'),
                ROI=('PL', 'mean'),
                Odd=('HA_Odd_H', 'mean') 
            ).reset_index().sort_values('Temporada', ascending=False)

            resumo['ROI'] = (resumo['ROI'] * 100).round(2).astype(str) + '%'
            resumo['Lucro'] = resumo['Lucro'].round(2)
            resumo['Odd'] = resumo['Odd'].round(2)

            st.dataframe(resumo, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # --- GRÁFICO ---
        st.subheader("📈 Curva de Lucro")
        fig = px.line(df_f, x='Date', y='Acumulado')
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

else:
    if not btn_rodar:
        st.info("Clique em 'Processar' para gerar a análise.")
