import streamlit as st
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import unicodedata

# Configuração da página
st.set_page_config(
    page_title="Conciliador de Mídia",
    page_icon="📊",
    layout="wide"
)

# ---------------------------------------------------------
# DICIONÁRIO DE SINÔNIMOS / DE-PARA DE PROGRAMAS
# Adicione novos apelidos e siglas aqui conforme necessário!
# ---------------------------------------------------------
SINONIMOS_PROGRAMAS = {
    "PIPP": ["PIPP", "PRIMEIRO IMPACTO", "PRIMEIRO IMPACTO PE"],
    "JN": ["JN", "JORNAL NACIONAL"],
    "BDPE": ["BDPE", "BOM DIA PE", "BOM DIA PERNAMBUCO"],
    "GE": ["GE", "GLOBO ESPORTE"],
    "CFT": ["CFT", "CALDEIRAO", "CALDEIRAO COM MION"]
}

def limpar_nome_programa(texto):
    if not texto:
        return ""
    texto = str(texto).upper().strip()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'\s+', ' ', texto)
    return texto

def obter_variacoes_programa(programa_ap):
    prog_limpo = limpar_nome_programa(programa_ap)
    # Procura se o programa da AP tem variações cadastradas
    for chave, variacoes in SINONIMOS_PROGRAMAS.items():
        if prog_limpo == chave or prog_limpo in [limpar_nome_programa(v) for v in variacoes]:
            return [limpar_nome_programa(v) for v in variacoes]
    # Se não houver variação cadastrada, retorna o próprio nome
    return [prog_limpo]

st.title("📊 Conciliador de Mídia - 3 Vias")
st.markdown("Faça o upload dos 3 PDFs da campanha para gerar a auditoria automática de faturamento.")

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1. AP (Matriz)")
    arquivo_ap = st.file_uploader("Envie a Autorização de Patrocínio", type=["pdf"], key="ap")

with col2:
    st.subheader("2. Mapa (Veículo)")
    arquivo_mapa = st.file_uploader("Envie o Mapa (Digital ou Escaneado)", type=["pdf"], key="mapa")

with col3:
    st.subheader("3. Auditoria (Comprovação)")
    arquivo_auditoria = st.file_uploader("Envie o relatório de Auditoria", type=["pdf"], key="auditoria")

st.divider()

if st.button("🔍 Conciliar Mídia", type="primary", use_container_width=True):
    if not (arquivo_ap and arquivo_mapa and arquivo_auditoria):
        st.error("⚠️ Por favor, faça o upload dos **3 arquivos** antes de prosseguir.")
    else:
        with st.spinner("Processando documentos e cruzando sinônimos... Aguarde..."):
            try:
                # 1. PROCESSANDO AP
                dados_ap = []
                with pdfplumber.open(arquivo_ap) as pdf:
                    for linha in pdf.pages[0].extract_text().split('\n'):
                        if "(" in linha and ")" in linha and "FONE" not in linha and "CLIENTE" not in linha:
                            nome_prog = linha.split(")")[0].split("(")[0].strip()
                            qtd = int(linha.split(")")[-1].strip().split()[-4])
                            dados_ap.append({"Programa": nome_prog, "Qtd_AP": qtd})
                
                tabela_ap = pd.DataFrame(dados_ap)
                tabela_ap["Programa"] = tabela_ap["Programa"].apply(limpar_nome_programa)
                tabela_ap = tabela_ap.groupby("Programa", as_index=False).sum()

                # Lista de programas base
                programas_ap = tabela_ap["Programa"].tolist()

                # 2. PROCESSANDO MAPA (OCR NATIVO COM BUSCA POR SINÔNIMOS)
                doc = fitz.open(stream=arquivo_mapa.read(), filetype="pdf")
                texto_mapa = ""
                for num_pagina in range(len(doc)):
                    pix = doc[num_pagina].get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    texto_mapa += pytesseract.image_to_string(img, lang='por') + "\n"

                dados_mapa = []
                for linha in texto_mapa.split('\n'):
                    linha_limpa = limpar_nome_programa(linha)
                    for prog in programas_ap:
                        variacoes = obter_variacoes_programa(prog)
                        if any(v in linha_limpa for v in variacoes):
                            numeros = re.findall(r'\b\d+\b', linha_limpa)
                            if numeros:
                                qtd = int(numeros[-1])
                                dados_mapa.append({"Programa": prog, "Qtd_Mapa": qtd})

                tabela_mapa = pd.DataFrame(dados_mapa)
                if not tabela_mapa.empty:
                    tabela_mapa = tabela_mapa.groupby("Programa", as_index=False).sum()
                else:
                    tabela_mapa = pd.DataFrame(columns=["Programa", "Qtd_Mapa"])

                # 3. PROCESSANDO AUDITORIA (BUSCA POR SINÔNIMOS)
                dados_auditoria = []
                with pdfplumber.open(arquivo_auditoria) as pdf:
                    for linha in pdf.pages[0].extract_text().split('\n'):
                        linha_limpa = limpar_nome_programa(linha)
                        for prog in programas_ap:
                            variacoes = obter_variacoes_programa(prog)
                            if any(v in linha_limpa for v in variacoes):
                                numeros = re.findall(r'\b\d+\b', linha_limpa)
                                if numeros:
                                    qtd = int(numeros[-1])
                                    dados_auditoria.append({"Programa": prog, "Qtd_Auditoria": qtd})

                tabela_auditoria = pd.DataFrame(dados_auditoria)
                if not tabela_auditoria.empty:
                    tabela_auditoria = tabela_auditoria.groupby("Programa", as_index=False).sum()
                else:
                    tabela_auditoria = pd.DataFrame(columns=["Programa", "Qtd_Auditoria"])

                # 4. CRUZAMENTO DIRETO
                df_final = pd.merge(tabela_ap, tabela_mapa, on="Programa", how="left").fillna(0)
                df_final = pd.merge(df_final, tabela_auditoria, on="Programa", how="left").fillna(0)

                df_final["Erro_Veiculo"] = df_final["Qtd_AP"] - df_final["Qtd_Mapa"]
                df_final["Erro_Auditoria"] = df_final["Qtd_AP"] - df_final["Qtd_Auditoria"]

                # RESULTADOS
                erros = df_final[(df_final["Erro_Veiculo"] != 0) | (df_final["Erro_Auditoria"] != 0)]

                if erros.empty:
                    st.success("✅ **TUDO OK PARA FATURAR!** Nenhuma divergência encontrada na conciliação.")
                else:
                    st.error("❌ **DIVERGÊNCIA ENCONTRADA!** Confira as diferenças abaixo:")
                    st.dataframe(erros[["Programa", "Qtd_AP", "Qtd_Mapa", "Qtd_Auditoria"]], use_container_width=True)

                st.subheader("📋 Tabela Completa do Cruzamento")
                st.dataframe(df_final, use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Conciliacao')
                
                st.download_button(
                    label="📥 Baixar Relatório em Excel",
                    data=buffer.getvalue(),
                    file_name="Relatorio_Conciliacao_Midia.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                st.error(f"❌ Ocorreu um erro ao processar os arquivos: {e}")
