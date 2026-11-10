import os
import json
import re
from flask import Flask, render_template, request, redirect, url_for, flash
import pypdf
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_para_flash_messages'

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

    # Data e Hora de criação
    data_criacao = ""
    hora_criacao = ""
    match_data_hora = re.search(r'Data/hora criação\s*(\d{2}/\d{2}/\d{4})\s*(\d{2}:\d{2}:\d{2})', texto)
    if match_data_hora:
        data_criacao = match_data_hora.group(1)
        hora_criacao = match_data_hora.group(2)

    # Nº chamada
    n_chamada = ""
    match_chamada = re.search(r'Nº chamada\s*(\d{4}-\d+-\d+)', texto)
    if match_chamada:
        n_chamada = match_chamada.group(1)

    # Número REDS
    n_reds = ""
    match_reds = re.search(r'Número REDS\s*(\d{4}-\d+-\d+)', texto)
    if match_reds:
        n_reds = match_reds.group(1)

    # Natureza (Captura código e descrição, limpando ruídos do final da linha)
    nat_6 = ""
    nat_resto = ""
    match_nat = re.search(r'([A-Z]\d{5})\s*-\s*([^\n]+)', texto)
    if match_nat:
        nat_6 = match_nat.group(1).strip()
        descricao_nat = match_nat.group(2).strip()
        
        # Remove lixos comuns, termos de metadados ou prioridades que venham grudados no final
        descricao_nat = re.sub(r'\s+(?:Não|Sim|Baixa|Média|Alta|Urgente|Data/hora|Unidade|Recurso).*$', '', descricao_nat, flags=re.IGNORECASE).strip()
        nat_resto = "- " + descricao_nat

    # Recurso
    recurso = ""
    match_recurso = re.search(r'Recurso\s*([A-Za-z0-9_-]+)', texto)
    if match_recurso:
        rec_bruto = match_recurso.group(1).strip()
        recurso = re.sub(r'Unidade.*$', '', rec_bruto, flags=re.IGNORECASE).strip()

    # Responsável registro
    resp_registro = ""
    match_resp = re.search(r'Responsável registro\s*([^\n]+)', texto)
    if match_resp:
        resp_registro = match_resp.group(1).strip()

    # Localização
    localizacao = ""
    match_loc = re.search(r'Localização\s*(.*?)(?:Complemento|Bairro|Histórico|Data/hora|\n\n)', texto, re.DOTALL | re.IGNORECASE)
    if match_loc:
        localizacao = match_loc.group(1).strip()
    else:
        match_rua = re.search(r'((?:RUA|AVENIDA|ALAMEDA|PRAÇA|RODOVIA|ESTRADA)\s+[^\n]+)', texto, re.IGNORECASE)
        if match_rua:
            localizacao = match_rua.group(1).strip()

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
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
        client = gspread.authorize(creds)
        
        sheet = client.open("GRADE DE OCORRÊNCIA").worksheet("GRADE DE OCORRÊNCIA")
        
        valores_coluna_b = sheet.col_values(2)
        proxima_linha = len(valores_coluna_b) + 1

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
        
        range_insercao = f"B{proxima_linha}:K{proxima_linha}"
        sheet.update(range_name=range_insercao, values=[valores_linha])
        return True, f"Dados inseridos com sucesso na linha {proxima_linha}!"
    except Exception as e:
        return False, str(e)

@app.route('/')
def index():
    dados = carregar_dados()
    return render_template('index.html', dados=dados)

@app.route('/processar', methods=['POST'])
def processar():
    if 'pdf_file' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('index'))
    
    file = request.files['pdf_file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('index'))
        
    temp_path = os.path.join('/tmp', file.filename)
    try:
        file.save(temp_path)
        dado_extraido = extrair_dados_pdf(temp_path)
        salvar_dado(dado_extraido)
        sucesso, msg = enviar_google_sheets(dado_extraido)
        
        if sucesso:
            flash('PDF carregado e dados enviados para o Google Sheets com sucesso!', 'success')
        else:
            flash(f'Erro no Google Sheets: {msg}', 'error')
    except Exception as e:
        flash(f'Erro ao processar o PDF: {str(e)}', 'error')
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)