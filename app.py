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
    csv_file = 'MEGA_BASE_HA_COMPLETA.csv'
    
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            cols_num = ['HG', 'AG', 'HA_Line', 'HA_Odd_H', 'HA_Odd_A', 'Odd_H', 'Odd_A']
            for c in cols_num:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            return df
        except Exception as e:
            st.error(f"Erro ao ler CSV: {e}")
            return None
    else:
        return None

# ==============================================================================
# 2. CÁLCULO DE LUCRO
# ==============================================================================
def calculate_pl(row, side, line_selected):
    if pd.isna(row['HA_Line']) or pd.isna(row['HA_Odd_H']) or pd.isna(row['HA_Odd_A']):
        return None

    hg, ag = row['HG'], row['AG']
    
    if side == 'Mandante':
        odd = row['HA_Odd_H']
        diff = hg - ag + line_selected 
    else: # Visitante
        odd = row['HA_Odd_A']
        diff = (ag - hg) - line_selected 

    stake = 1.0
    
    if diff > 0.25: return (odd - 1) * stake       # Green
    elif diff < -0.25: return -stake               # Red
    elif abs(diff) < 0.01: return 0.0              # Void
    elif diff > 0: return ((odd - 1) * stake) / 2  # Half-Win
    else: return -stake / 2                        # Half-Loss

# ==============================================================================
# 3. INTERFACE E LÓGICA DE ESTADO
# ==============================================================================
st.title("🎯 Sniper HA - Validador de Estratégias")

df = load_data()

if df is None:
    st.error("⚠️ Arquivo 'MEGA_BASE_HA_COMPLETA.csv' não encontrado.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuração da Estratégia")

# 1. Competição
if 'Competicao' in df.columns:
    ligas = sorted(df['Competicao'].unique().astype(str))
    liga_sel = st.sidebar.selectbox("Competição", ligas)
    df_liga = df[df['Competicao'] == liga_sel].copy()
else:
    st.error("Coluna 'Competicao' inexistente.")
    st.stop()

# 2. Lado
lado_sel = st.sidebar.radio("Apostar em:", ['Mandante', 'Visitante'])

# 3. Lógica de Linhas com MEMÓRIA (Persistência)
available_lines = sorted(df_liga['HA_Line'].dropna().unique())

if lado_sel == 'Visitante':
    display_lines = sorted([-x for x in available_lines])
else:
    display_lines = available_lines

if not display_lines:
    st.warning("Sem dados de Handicap para esta liga.")
    st.stop()

# --- ALGORITMO DE PERSISTÊNCIA DA LINHA ---
# Verifica qual foi a última linha salva na sessão
last_line = st.session_state.get('ultima_linha_selecionada', -0.5)

# Tenta encontrar o índice dessa linha na nova lista de linhas da liga atual
try:
    index_padrao = display_lines.index(last_line)
except ValueError:
    # Se a linha antiga não existe nesta liga, tenta achar o -0.5 ou 0.0 como fallback
    if -0.5 in display_lines:
        index_padrao = display_lines.index(-0.5)
    elif 0.0 in display_lines:
        index_padrao = display_lines.index(0.0)
    else:
        index_padrao = 0

# Cria o widget com o índice calculado
linha_sel = st.sidebar.selectbox(
    "Linha de Handicap", 
    display_lines, 
    index=index_padrao
)

# Salva a escolha atual na sessão para a próxima rodada
st.session_state['ultima_linha_selecionada'] = linha_sel

# --- BOTÃO DE RODAR ---
st.sidebar.markdown("---")
btn_rodar = st.sidebar.button("🚀 Rodar Análise", type="primary")

# ==============================================================================
# 4. PROCESSAMENTO (SÓ RODA SE CLICAR NO BOTÃO)
# ==============================================================================

# Usamos session_state para manter o resultado na tela após clicar, 
# caso contrário, qualquer interação simples poderia sumir com os dados.
if btn_rodar:
    st.session_state['mostrar_resultados'] = True
    st.session_state['params_analise'] = (liga_sel, lado_sel, linha_sel)

# Verifica se deve mostrar resultados
if st.session_state.get('mostrar_resultados'):
    
    # Recupera parâmetros que foram "Rodados" (para garantir consistência)
    # Se o usuário mudar a liga mas não clicar em rodar, os dados velhos continuam ou somem?
    # Vamos fazer com que mostre os dados ATUAIS selecionados quando o botão foi ativado.
    
    # Filtro no DB
    if lado_sel == 'Mandante':
        db_line_target = linha_sel
        odd_col = 'HA_Odd_H'
    else:
        db_line_target = linha_sel * -1
        odd_col = 'HA_Odd_A'

    df_filtrado = df_liga[df_liga['HA_Line'] == db_line_target].copy()

    if df_filtrado.empty:
        st.warning("Nenhum jogo encontrado com esta linha nesta competição.")
    else:
        # Cálculos
        df_filtrado['PL'] = df_filtrado.apply(lambda row: calculate_pl(row, lado_sel, linha_sel), axis=1)
        df_filtrado = df_filtrado.dropna(subset=['PL'])
        
        if 'Date' in df_filtrado.columns:
            df_filtrado['Date'] = pd.to_datetime(df_filtrado['Date'])
            df_filtrado = df_filtrado.sort_values('Date')
            df_filtrado['Lucro_Acumulado'] = df_filtrado['PL'].cumsum()

        # --- EXIBIÇÃO ---
        st.markdown(f"### 📊 Resultado: {liga_sel} | {lado_sel} {linha_sel}")
        
        total_jogos = len(df_filtrado)
        lucro_total = df_filtrado['PL'].sum()
        roi_total = (lucro_total / total_jogos) * 100
        odd_media_total = df_filtrado[odd_col].mean()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Volume", f"{total_jogos}")
        c2.metric("Lucro Total", f"{lucro_total:.2f} u", delta_color="normal")
        c3.metric("ROI Global", f"{roi_total:.2f}%", delta=f"{roi_total:.2f}%")
        c4.metric("Odd Média", f"{odd_media_total:.2f}")

        st.divider()

        # Tabela por Temporada
        st.markdown("### 📅 Desempenho por Temporada")
        if 'Temporada' in df_filtrado.columns:
            resumo = df_filtrado.groupby('Temporada').agg(
                Jogos=('PL', 'count'),
                Lucro=('PL', 'sum'),
                ROI=('PL', 'mean'),
                Odd_Media=(odd_col, 'mean')
            ).reset_index()

            resumo_show = resumo.copy()
            resumo_show['ROI'] = (resumo_show['ROI'] * 100).round(2).astype(str) + '%'
            resumo_show['Lucro'] = resumo_show['Lucro'].round(2)
            resumo_show['Odd_Media'] = resumo_show['Odd_Media'].round(2)
            resumo_show = resumo_show.sort_values('Temporada', ascending=False)

            st.dataframe(
                resumo_show, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Temporada": st.column_config.TextColumn("Temporada"),
                    "Jogos": st.column_config.NumberColumn("Jogos", format="%d"),
                    "Lucro": st.column_config.NumberColumn("Lucro (u)", format="%.2f"),
                    "ROI": st.column_config.TextColumn("ROI %"),
                    "Odd_Media": st.column_config.NumberColumn("Odd Média", format="%.2f")
                }
            )
        
        st.divider()
        
        # Gráfico
        st.markdown("### 📈 Curva de Lucro")
        fig = px.line(df_filtrado, x='Date', y='Lucro_Acumulado', height=400)
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

else:
    if not btn_rodar:
        st.info("👈 Selecione os filtros na barra lateral e clique em 'Rodar Análise'.")
