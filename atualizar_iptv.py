import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import requests

# Configurações de Fuso Horário e Intervalo de Datas para buscar o EPG
AGORA_UTC = datetime.utcnow()
HOJE_DATA = AGORA_UTC.replace(hour=3, minute=0, second=0, microsecond=0)
AMANHA_DATA = HOJE_DATA + timedelta(days=1)

START_TIME_GTE = HOJE_DATA.strftime("%Y-%m-%dT%H:%M:%S.000Z")
START_TIME_LT = AMANHA_DATA.strftime("%Y-%m-%dT%H:%M:%S.000Z")

# Chave de autenticação extraída dos cabeçalhos fornecidos
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ1amp0eG1nenFzZ2l6Z3N4YWZqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQwMDQ5NjEsImV4cCI6MjA2OTU4MDk2MX0.yL3dHtaHZDk5fjCET06n7YsG3UJTmhq6-qwhwIsXoww"

HEADERS = {
    "apikey": API_KEY,
    "authorization": f"Bearer {API_KEY}",
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "accept": "*/*",
    "origin": "https://batistaplay.net",
    "referer": "https://batistaplay.net/"
}

def gerar_programacao_fallback():
    """Gera blocos contínuos de 2 horas preenchendo as 24h para canais sem EPG oficial."""
    programas = []
    base_time = HOJE_DATA
    
    for i in range(12):
        inicio = base_time + timedelta(hours=i*2)
        fim = inicio + timedelta(hours=2)
        programas.append({
            "title": "Programação Regular do Canal",
            "description": "Programação Regular do Canal 24/7. Conteúdo variado e entretenimento contínuo.",
            "start_time": inicio.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "end_time": fim.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        })
    return programas

def formatar_para_xmltv(data_iso_str):
    """Converte formato ISO do Supabase para o formato padrão do XMLTV."""
    try:
        dt = datetime.strptime(data_iso_str.split(".")[0], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S +0000")
    except:
        return data_iso_str

def buscar_epg_da_api(channel_id):
    """Interroga a API de epg_programs filtrando pelo ID único do canal."""
    epg_url = (
        f"https://vujjtxmgzqsgizgsxafj.supabase.co/rest/v1/epg_programs"
        f"?select=*&channel_id=eq.{channel_id}"
        f"&start_time=gte.{START_TIME_GTE}&start_time=lt.{START_TIME_LT}"
        f"&order=start_time.asc"
    )
    try:
        response = requests.get(epg_url, headers=HEADERS, timeout=7)
        if response.status_code == 200:
            dados = response.json()
            if dados:  # Retorna se encontrar uma lista preenchida
                return dados
    except Exception as e:
        print(f"     [!] Erro na API de EPG para o canal {channel_id}: {e}")
    return None

def processar_tudo():
    channels_url = "https://vujjtxmgzqsgizgsxafj.supabase.co/rest/v1/channels?select=*%2Ccategories%28name%29&is_active=eq.true&order=channel_number.asc"
    
    print("[->] Coletando canais ativos do Supabase...")
    try:
        res_channels = requests.get(channels_url, headers=HEADERS)
        if res_channels.status_code != 200:
            print(f"Erro ao obter canais: {res_channels.status_code}")
            return
        canais = res_channels.json()
    except Exception as e:
        print(f"Erro na conexão: {e}")
        return

    # =========================================================
    # PASSO 1: GERAR ARQUIVO DE STREAMS (BatistaPlay.m3u8)
    # =========================================================
    print("[->] Criando lista de reprodução M3U8...")
    m3u_content = "#EXTM3U\n"
    
    for canal in canais:
        uuid_canal = canal.get("id")
        nome_canal = canal.get("name", "Sem Nome")
        logo = canal.get("logo_url", "")
        stream = canal.get("stream_url", "")
        numero = canal.get("channel_number", "")
        
        categoria_obj = canal.get("categories")
        categoria = categoria_obj.get("name", "Geral") if isinstance(categoria_obj, dict) else "Geral"
        
        # O tvg-id recebe exatamente o UUID para casar perfeitamente com o arquivo XML
        m3u_content += (
            f'#EXTINF:-1 tvg-id="{uuid_canal}" tvg-name="{nome_canal}" '
            f'tvg-logo="{logo}" group-title="{categoria}",{numero} - {nome_canal}\n'
        )
        m3u_content += f"{stream}\n"
        
    with open("BatistaPlay.m3u8", "w", encoding="utf-8") as f:
        f.write(m3u_content)
    print("[✓] Arquivo 'BatistaPlay.m3u8' exportado com sucesso!")

    # =========================================================
    # PASSO 2: GERAR ARQUIVO DE PROGRAMAÇÃO (BatistaPlay_EPG.xml)
    # =========================================================
    print("[->] Estruturando Guia de Programação XMLTV...")
    root = ET.Element("tv")

    # Mapeia cabeçalho de canais no XML
    for canal in canais:
        id_canal = canal.get("id")
        nome_canal = canal.get("name", "Canal Sem Nome")
        
        channel_elem = ET.SubElement(root, "channel", id=id_canal)
        ET.SubElement(channel_elem, "display-name").text = f"{canal.get('channel_number')} - {nome_canal}"
        if canal.get("logo_url"):
            ET.SubElement(channel_elem, "icon", src=canal.get("logo_url"))

    # Mapeia a grade de horários
    for canal in canais:
        channel_id = canal.get("id")
        nome_canal = canal.get("name")
        
        programas_do_canal = buscar_epg_da_api(channel_id)
        
        if programas_do_canal:
            print(f"  [API] Programação real encontrada para: {nome_canal}")
        else:
            print(f"  [EPG Automático] Inserindo grade 24/7 para: {nome_canal}")
            programas_do_canal = gerar_programacao_fallback()

        for prog in programas_do_canal:
            start_xmltv = formatar_para_xmltv(prog.get("start_time"))
            stop_xmltv = formatar_para_xmltv(prog.get("end_time"))
            
            programme_elem = ET.SubElement(
                root, "programme",
                start=start_xmltv,
                stop=stop_xmltv,
                channel=channel_id
            )
            
            ET.SubElement(programme_elem, "title", lang="pt").text = prog.get("title", "Programação Regular")
            ET.SubElement(programme_elem, "desc", lang="pt").text = prog.get("description") or "Programação Regular do Canal."

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ", level=0)
    tree.write("BatistaPlay_EPG.xml", encoding="utf-8", xml_declaration=True)
    print("[✓] Arquivo 'BatistaPlay_EPG.xml' exportado com sucesso!")
    print("\n[Operação Concluída] Ambos os arquivos estão prontos para uso sincronizado.")

if __name__ == "__main__":
    processar_tudo()
