import os
import json
import re
from flask import Flask, render_template, request, redirect, url_for
import pypdf
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

DB_FILE = 'banco_dados.json'

def carregar_dados():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def salvar_dado(dado):
    dados = carregar_dados()
    dados.append(dado)
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def extrair_dados_pdf(caminho_pdf):
    reader = pypdf.PdfReader(caminho_pdf)
    texto = ""
    for page in reader.pages:
        texto += page.extract_text() or ""

    # Data e Hora de criação (ex: 05/11/2026 20:39:01)
    data_criacao = ""
    hora_criacao = ""
    match_data_hora = re.search(r'Data/hora criação\s*(\d{2}/\d{2}/\d{4})\s*(\d{2}:\d{2}:\d{2})', texto)
    if match_data_hora:
        data_criacao = match_data_hora.group(1)
        hora_criacao = match_data_hora.group(2)

    # Nº chamada (ex: 2026-48695233-9)
    n_chamada = ""
    match_chamada = re.search(r'Nº chamada\s*(\d{4}-\d+-\d+)', texto)
    if match_chamada:
        n_chamada = match_chamada.group(1)

    # Número REDS (ex: 2026-051633994-001)
    n_reds = ""
    match_reds = re.search(r'Número REDS\s*(\d{4}-\d+-\d+)', texto)
    if match_reds:
        n_reds = match_reds.group(1)

    # Natureza (ex: V01015 - VITIMA COM HEMORRAGIA)
    nat_6 = ""
    nat_resto = ""
    match_nat = re.search(r'([A-Z]\d{5})\s*-\s*([^Não\n]+)', texto)
    if match_nat:
        nat_6 = match_nat.group(1).strip()
        nat_resto = "- " + match_nat.group(2).strip()

    # Recurso (ex: UR1039)
    recurso = ""
    match_recurso = re.search(r'Recurso\s*(UR\d+)', texto)
    if match_recurso:
        recurso = match_recurso.group(1)

    # Responsável registro (ex: 3 SGT FILIPE BAGETO MOREIRA (BM1362177))
    resp_registro = ""
    match_resp = re.search(r'Responsável registro\s*([^\n]+)', texto)
    if match_resp:
        resp_registro = match_resp.group(1).strip()

    # Localização
    localizacao = ""
    match_loc = re.search(r'Localização\s*(.*?)Complemento', texto, re.DOTALL)
    if match_loc:
        localizacao = match_loc.group(1).strip()
    else:
        match_rua = re.search(r'(RUA\s+[^\n]+)', texto)
        if match_rua:
            localizacao = match_rua.group(1).replace('Complemento', '').strip()

    dado = {
        "data": data_criacao,
        "hora": hora_criacao,
        "n_chamada": n_chamada,
        "n_reds": n_reds,
        "nat_6": nat_6,
        "recurso": recurso,
        "resp_registro": resp_registro,
        "nat_resto": nat_resto,
        "localizacao": localizacao
    }
    
    print("DADOS EXATOS EXTRAÍDOS:", dado)
    return dado

def enviar_google_sheets(dado):
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        
        # Abre o arquivo "GRADE DE OCORRÊNCIA" na aba "GRADE DE OCORRÊNCIA"
        sheet = client.open("GRADE DE OCORRÊNCIA").worksheet("GRADE DE OCORRÊNCIA")
        
        # Obtém todos os valores preenchidos na Coluna B
        valores_coluna_b = sheet.col_values(2)
        
        # Descobre a próxima linha totalmente vazia a partir da Coluna B
        proxima_linha = len(valores_coluna_b) + 1

        # Dados estruturados da Coluna B até K (Coluna A e J mantidas vazias)
        valores_linha = [
            dado['data'],          # Coluna B
            dado['hora'],          # Coluna C
            dado['n_chamada'],     # Coluna D
            dado['n_reds'],        # Coluna E
            dado['nat_6'],         # Coluna F
            dado['recurso'],       # Coluna G
            dado['resp_registro'], # Coluna H
            dado['nat_resto'],     # Coluna I
            "",                    # Coluna J (Vazia)
            dado['localizacao']    # Coluna K
        ]
        
        # Atualiza o intervalo exato na planilha (B{linha}:K{linha})
        range_insercao = f"B{proxima_linha}:K{proxima_linha}"
        sheet.update(range_name=range_insercao, values=[valores_linha])
        
        print(f"✅ Dados inseridos com sucesso na linha {proxima_linha} (Aba GRADE DE OCORRÊNCIA)!")
        return True
    except Exception as e:
        print(f"❌ ERRO GOOGLE SHEETS: {e}")
        return False

@app.route('/')
def index():
    dados = carregar_dados()
    return render_template('index.html', dados=dados)

@app.route('/processar', methods=['POST'])
def processar():
    if 'pdf_file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['pdf_file']
    if file.filename != '':
        temp_path = os.path.join('/tmp', file.filename)
        file.save(temp_path)
        
        dado_extraido = extrair_dados_pdf(temp_path)
        salvar_dado(dado_extraido)
        enviar_google_sheets(dado_extraido)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)