"""J-PlatPat から特許情報を取得するサービス。

探索スクリプト (explore_jplatpat*.py) で確認した内部 API フロー:
1. POST /web/patnumber/wsp0102  → ISN / HASH_VALUE を取得
2. 検索結果行の公開番号リンクをクリック → 新タブで /p0200 (文献表示ページ) が開く
3. /p0200 ページ内で以下の API を呼び出して各セクションを取得:
   - POST /app/comdocu/wsp1101  → 文書存在フラグ (DOCU_EXISTS_FLG_INFO)
   - POST /app/comdocu/wsp1201  → 書誌情報 (SPC_NUM=1)
   - POST /app/comdocu/wsp1202  → 要約 (SPC_NUM=2)
   - POST /app/comdocu/wsp1203  → 請求の範囲 (SPC_NUM=3, 必要時)
   - POST /app/comdocu/wsp1204  → 詳細な説明 (SPC_NUM=4, 必要時)
   - POST /app/comdocu/wsp3101  → gazette パス / 図面リンク

Phase 1: 単一特許の取得 (番号照会 → 文献表示)
Phase 2: 検索式による一括取得 (別途実装)
"""

import re
import json
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ========== データクラス ==========

@dataclass
class PatentFigure:
    """特許図面の参照情報。図面は都度オンデマンドで取得（ローカル保存しない）。"""
    figure_number: str
    url: str
    description: str = ""


@dataclass
class PatentBiblio:
    """書誌情報。"""
    patent_number: str           # 公開番号 (例: 特開2020-060350)
    title: str = ""              # 発明の名称
    applicant: str = ""          # 出願人
    inventor: str = ""           # 発明者
    filing_date: str = ""        # 出願日
    publication_date: str = ""   # 公開日
    ipc_codes: str = ""          # 国際特許分類
    fi_codes: str = ""           # FI コード
    app_number: str = ""         # 出願番号
    status: str = ""             # ステータス
    # 内部識別子（API 呼び出し時に使用）
    isn: str = ""
    hash_value: str = ""
    docu_key_jpa: str = ""       # "JPA 502060350" 形式


@dataclass
class PatentDocument:
    """書誌情報 + テキスト + 図面参照。"""
    biblio: PatentBiblio
    abstract: str = ""           # 要約
    claims_text: str = ""        # 請求の範囲 (全文)
    description_text: str = ""   # 詳細な説明 (全文)
    figures: list[PatentFigure] = field(default_factory=list)
    # 元データ (HTML/XML テキスト)
    raw_biblio_html: str = ""
    raw_abstract_html: str = ""
    raw_claims_html: str = ""
    raw_description_html: str = ""


# ========== 番号正規化 ==========

def normalize_patent_number(patent_number: str) -> str:
    """入力された特許番号を番号照会入力形式 (例: 2020-060350) に正規化する。

    対応形式:
    - 特開2020-060350  → 2020-060350
    - JP2020060350A    → 2020-060350  (JP + 年4桁 + 番号6桁 + 種別)
    - 2020-060350      → 2020-060350  (そのまま)
    - 特許6123456      → 6123456      (登録番号)
    """
    s = patent_number.strip()

    # "特開", "特許", "特願", "実開", "実登" 等のプレフィックスを除去
    s = re.sub(r'^(特開|特許|特願|実開|実登|実願|特表|再公表特許)', '', s)

    # JP2020060350A 形式 (JP + 年4桁 + 番号 + 種別)
    m = re.match(r'^JP(\d{4})(\d{6,7})[A-Z]?$', s.upper())
    if m:
        year, num = m.group(1), m.group(2)
        return f"{year}-{num.lstrip('0').zfill(6) if len(num) == 7 else num}"

    # すでに 2020-060350 形式
    if re.match(r'^\d{4}-\d{1,9}$', s):
        return s

    # 数字のみ (登録番号等)
    if re.match(r'^\d{6,10}$', s):
        return s

    # それ以外はそのまま渡す
    return s


# ========== HTML → テキスト変換 ==========

def html_to_text(html: str) -> str:
    """J-PlatPat の TEXT_DATA (HTML ライク) からプレーンテキストを抽出する。"""
    if not html:
        return ""
    # SDO タグ等の独自タグを除去
    text = re.sub(r'<SDO[^>]*>', '', html)
    text = re.sub(r'</SDO>', '', text)
    text = re.sub(r'<DP[^>]*>', '', text)
    text = re.sub(r'</DP>', '', text)
    text = re.sub(r'<RTI[^>]*>', '', text)
    text = re.sub(r'</RTI>', '', text)
    # img タグを除去 (図は別途参照)
    text = re.sub(r'<img[^>]*>', '', text)
    # <br> を改行に変換
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    # 残りの HTML タグを除去
    text = re.sub(r'<[^>]+>', '', text)
    # 連続する空白行を整理
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ========== 書誌情報パース ==========

_FULLWIDTH_TABLE = str.maketrans(
    'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ'
    'ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ'
    '０１２３４５６７８９　／',
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '0123456789 /'
)


def normalize_fullwidth(text: str) -> str:
    """全角英数字・スペース・スラッシュを半角に変換する。"""
    return text.translate(_FULLWIDTH_TABLE)


def parse_biblio(text: str) -> dict:
    """TEXT_DATA (書誌) からキー情報を抽出する。"""
    result = {}

    # 発明の名称
    m = re.search(r'【発明の名称】\s*(.+)', text)
    if m:
        result["title"] = m.group(1).strip()

    # 出願番号
    m = re.search(r'【出願番号】\s*(.+)', text)
    if m:
        result["app_number"] = m.group(1).strip()

    # 公開番号
    m = re.search(r'【公開番号】\s*(.+)', text)
    if m:
        result["patent_number"] = m.group(1).strip()

    # 公開日
    m = re.search(r'【公開日】\s*(.+)', text)
    if m:
        result["publication_date"] = m.group(1).strip()

    # 出願日
    m = re.search(r'【出願日】\s*(.+)', text)
    if m:
        result["filing_date"] = m.group(1).strip()

    # 出願人・代理人・発明者のセクション構造を解析
    # 書誌情報は [(71)【出願人】 ... (74)【代理人】 ... (72)【発明者】 ...] の順
    # 各セクションの【氏名又は名称】または【氏名】を抽出する
    applicant_section = re.search(
        r'【出願人】(.*?)(?=【代理人】|【発明者】|【テーマコード】|$)', text, re.DOTALL
    )
    if applicant_section:
        names = re.findall(r'【氏名又は名称】\s*(.+)', applicant_section.group(1))
        if names:
            result["applicant"] = " / ".join(n.strip() for n in names[:5])

    inventor_section = re.search(
        r'【発明者】(.*?)(?=【テーマコード】|【Ｆターム】|$)', text, re.DOTALL
    )
    if inventor_section:
        names = re.findall(r'【氏名】\s*(.+)', inventor_section.group(1))
        if names:
            result["inventor"] = " / ".join(n.strip() for n in names[:5])

    # 国際特許分類 (全角 → 半角変換してから抽出)
    normalized = normalize_fullwidth(text)
    ipc_section = re.search(
        r'(?:国際特許分類|IPC)(.*?)(?=【FI】|【Fターム】|【F-term】|【テーマコード】|$)',
        normalized, re.DOTALL
    )
    if ipc_section:
        ipc_matches = re.findall(r'([A-HY]\d{2}[A-Z]\s*\d+/\d+)', ipc_section.group(1))
        if ipc_matches:
            result["ipc_codes"] = " / ".join(list(dict.fromkeys(ipc_matches))[:8])
    else:
        # 全文から IPC パターン検索 (fallback)
        ipc_matches = re.findall(r'([A-HY]\d{2}[A-Z]\s+\d+/\d+)', normalized)
        if ipc_matches:
            result["ipc_codes"] = " / ".join(list(dict.fromkeys(ipc_matches))[:8])

    # FI コード
    fi_section = re.search(
        r'【FI】(.*?)(?=【Fターム】|【テーマコード】|【審査請求】|$)',
        normalized, re.DOTALL
    )
    if fi_section:
        fi_matches = re.findall(r'([A-HY]\d{2}[A-Z]\s*[\d/]+[^\n]*)', fi_section.group(1))
        if fi_matches:
            result["fi_codes"] = " / ".join(f.strip() for f in fi_matches[:8])

    return result


# ========== メインスクレイパー ==========

async def fetch_patent(patent_number: str) -> PatentDocument:
    """特許番号から J-PlatPat で書誌情報・本文・図面参照を取得する。

    Args:
        patent_number: 特開2020-123456 / JP2020123456A / 2020-060350 等の形式

    Returns:
        PatentDocument (書誌情報 + 要約 + 請求項 + 詳細説明 + 図面参照)

    Raises:
        ValueError: 特許が見つからない場合
        RuntimeError: スクレイピング中のエラー
    """
    import concurrent.futures

    normalized = normalize_patent_number(patent_number)
    logger.info(f"J-PlatPat 取得開始: {patent_number} → {normalized}")

    # Windows の asyncio (ProactorEventLoop / SelectorEventLoop 両方) は
    # サブプロセス生成と add_reader() を同時にサポートできないため Playwright async API が動作しない。
    # sync_playwright をスレッドプール内で実行することで回避する。
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _run_playwright_in_thread, normalized)


def _run_playwright_in_thread(normalized_number: str) -> PatentDocument:
    """Playwright 同期 API をスレッド内で実行する（asyncio 非依存）。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale="ja-JP")
            return _scrape_patent_sync(context, normalized_number)
        finally:
            browser.close()


def _scrape_patent_sync(context, normalized_number: str) -> PatentDocument:
    """Playwright 同期コンテキストを使って特許データをスクレイピングする。"""
    page = context.new_page()

    wsp_response: dict = {}

    def capture_wsp_search(response):
        # 番号照会 (wsp0102) と 簡易検索 (wsp0103) 両方に対応
        if ("wsp0102" in response.url or "wsp0103" in response.url) and response.status == 200:
            try:
                data = response.json()
                lst = data.get("SEARCH_RSLT_LIST") or []
                if lst:
                    wsp_response["item"] = lst[0]
                    disp = lst[0].get("PUBLI_NUM_DISP", "")
                    if disp:
                        wsp_response["docu_key"] = disp
            except Exception:
                pass

    page.on("response", capture_wsp_search)

    try:
        # ---- ステップ1: J-PlatPat トップページを開く ----
        logger.debug("J-PlatPat トップページへ移動")
        page.goto("https://www.j-platpat.inpit.go.jp/", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)

        # ---- ステップ2 & 3: 検索 (番号種別で分岐) ----
        # 数字のみ → 登録番号 → 簡易検索 (wsp0103)
        # 年号-連番 → 公開番号 → 番号照会 (wsp0102)
        if re.match(r'^\d{6,10}$', normalized_number):
            # 簡易検索: Angular フォームに値をセットしてから検索ボタンをクリック
            query = f"特許{normalized_number}"
            logger.debug(f"簡易検索: {query}")
            page.evaluate("""(val) => {
                const input = document.getElementById('s01_srchCondtn_txtSimpleSearch');
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, val);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }""", query)
            page.wait_for_timeout(500)
            page.click("#s01_srchBtn_btnSearch")
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(3000)
        else:
            # 番号照会
            logger.debug(f"番号照会: {normalized_number}")
            page.click("#cfc001_globalNav_item_0")
            page.wait_for_timeout(300)
            page.click("#cfc001_globalNav_sub_item_0_0")
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            page.locator("#p00_srchCondtn_txtDocNoInputNo1").fill(normalized_number)
            page.wait_for_timeout(500)
            page.click("#p00_searchBtn_btnDocInquiry")
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(3000)

        # ---- ステップ4: 検索結果の確認 ----
        item = wsp_response.get("item", {})
        isn = item.get("ISN", "")
        hash_value = item.get("HASH_VALUE", "")
        publi_num_internal = item.get("PUBLI_NUM", "")
        docu_key = wsp_response.get("docu_key", f"特開{normalized_number}")
        docu_key_jpa = _make_jpa_key(publi_num_internal)

        if not isn:
            raise ValueError(f"特許番号 {normalized_number} が J-PlatPat で見つかりませんでした。")

        logger.debug(f"ISN={isn}, DOCU_KEY={docu_key}, JPA_KEY={docu_key_jpa}")

        # ---- ステップ5: 公開番号リンクをクリック → 新タブで p0200 が開く ----
        logger.debug("公開番号リンクをクリックして文献表示ページへ移動")
        with context.expect_page() as new_page_info:
            page.locator("td#patentUtltyIntnlNumOnlyLst_tableView_publicNumArea a").first.click()

        detail_page = new_page_info.value
        try:
            detail_page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        detail_page.wait_for_timeout(5000)

        # ---- ステップ6〜9: 各セクションを取得 ----
        logger.debug("書誌情報 (wsp1201) 取得")
        biblio_data = _call_api_sync(detail_page, "/app/comdocu/wsp1201", {
            "DOCU_KEY": docu_key, "ACQUISITION_MODE": "0", "SPC_NUM": 1,
            "TOTAL_PAGE_CNT": 0, "USE_OF_LANG": "ja", "WABUN_EIBUN": "0",
            "BLOCK_NUM": 0, "ISN": isn, "OTID": None,
        })

        logger.debug("要約 (wsp1202) 取得")
        abstract_data = _call_api_sync(detail_page, "/app/comdocu/wsp1202", {
            "DOCU_KEY": docu_key, "ACQUISITION_MODE": "0", "SPC_NUM": 2,
            "TOTAL_PAGE_CNT": 0, "USE_OF_LANG": "ja", "WABUN_EIBUN": "0",
            "BLOCK_NUM": 0, "ISN": isn, "OTID": None,
        })

        logger.debug("請求の範囲 (wsp1203) 取得")
        claims_data = _call_api_sync(detail_page, "/app/comdocu/wsp1203", {
            "DOCU_KEY": docu_key, "ACQUISITION_MODE": "0", "SPC_NUM": 3,
            "TOTAL_PAGE_CNT": 0, "USE_OF_LANG": "ja", "WABUN_EIBUN": "0",
            "BLOCK_NUM": 0, "ISN": isn, "OTID": None,
        })

        logger.debug("詳細な説明 (wsp1204) 取得")
        desc_data = _call_api_sync(detail_page, "/app/comdocu/wsp1204", {
            "DOCU_KEY": docu_key, "ACQUISITION_MODE": "0", "SPC_NUM": 4,
            "TOTAL_PAGE_CNT": 0, "USE_OF_LANG": "ja", "WABUN_EIBUN": "0",
            "BLOCK_NUM": 0, "ISN": isn, "OTID": None,
        })

        # ---- ステップ10: 図面リンク (wsp3101) を取得 ----
        logger.debug("図面リンク (wsp3101) 取得")
        figures = []
        if docu_key_jpa and hash_value:
            gazette_data = _call_api_sync(detail_page, "/app/comdocu/wsp3101", {
                "DOCU_KEY": docu_key_jpa,
                "OVERVIEW_AREA_DATA_EXISTS_FLG": 1,
                "DRAWING_AREA_DATA_EXISTS_FLG": 1,
                "CDN_HASH": hash_value,
            })
            figures = _parse_figures(gazette_data, hash_value)

        # ---- データ組み立て ----
        raw_biblio = biblio_data.get("DOCU_DATA", {}).get("TEXT_DATA", "")
        raw_abstract = abstract_data.get("DOCU_DATA", {}).get("TEXT_DATA", "")
        raw_claims = claims_data.get("DOCU_DATA", {}).get("TEXT_DATA", "")
        raw_desc = desc_data.get("DOCU_DATA", {}).get("TEXT_DATA", "")

        biblio_fields = parse_biblio(html_to_text(raw_biblio))

        biblio = PatentBiblio(
            patent_number=biblio_fields.get("patent_number", normalized_number),
            title=biblio_fields.get("title", ""),
            applicant=biblio_fields.get("applicant", ""),
            inventor=biblio_fields.get("inventor", ""),
            filing_date=biblio_fields.get("filing_date", ""),
            publication_date=biblio_fields.get("publication_date", ""),
            ipc_codes=biblio_fields.get("ipc_codes", ""),
            fi_codes=biblio_fields.get("fi_codes", ""),
            app_number=biblio_fields.get("app_number", ""),
            isn=isn,
            hash_value=hash_value,
            docu_key_jpa=docu_key_jpa,
        )

        return PatentDocument(
            biblio=biblio,
            abstract=html_to_text(raw_abstract),
            claims_text=html_to_text(raw_claims),
            description_text=html_to_text(raw_desc),
            figures=figures,
            raw_biblio_html=raw_biblio,
            raw_abstract_html=raw_abstract,
            raw_claims_html=raw_claims,
            raw_description_html=raw_desc,
        )

    finally:
        page.close()


# ========== ヘルパー関数 ==========

def _make_jpa_key(publi_num: str) -> str:
    """内部公開番号 (例: '0102020060350') から JPA キー (例: 'JPA 502060350') を生成する。

    内部番号のフォーマット: 01 + 年4桁 + 番号7桁 = 13桁
    JPA キー: JPA + 番号7桁のうち後7桁 (先頭の年を除いた部分)
    """
    if not publi_num:
        return ""
    # "0102020060350" → 年=2020, 番号=060350
    # gazette path から確認: /gazette_work/domestic/A/502060000/502060300/502060350/
    # JPA キーは "JPA " + 年2桁 + 番号7桁? → "JPA 502060350"
    # 502060350 = 50 + 2060350?  → 50 は何か
    # wsp3101 では DOCU_KEY: "JPA 502060350"
    # gazette path: .../502060000/502060300/502060350/...
    # publi_num "0102020060350": 01=法律区分(JP特許), 2020=年4桁, 0060350=番号7桁
    # JPA キー = "JPA " + 5 + 年下2桁 + 番号7桁
    # = "JPA " + "5" + "20" + "0060350" = "JPA 5200060350" (10桁)? 違う
    # gazette path では 502060350 (9桁)
    # 番号 0060350 (7桁) → 先頭0を除くと 60350 (5桁)
    # 年 2020 → 20 (2桁)
    # → "5" + "02" + "060350" = "502060350" → これが合う!
    # 但し 02 は年 2020 の下2桁ではなく "02" = 2020-2018=2? 令和2年?
    # 正式には gazette path = "5" + 平成換算年? + 番号6桁
    # 令和2年=2020 → 2 → "502060350"?
    # 令和元年=2019 → 1, 平成30年=2018 → 30
    # でも "5" + "02" + "060350" = "502060350" で実際の値と一致
    # "02" は 2020年 → (2020 - 2018) = 2 → 2桁0埋め "02"?
    # 平成30年=2018=30: "5" + "30" = "530"
    # 令和元年=2019=1: "5" + "01" = "501"
    # 令和2年=2020=2: "5" + "02" = "502" ← これが合う!
    # なので JPA キー = "JPA 5{令和年号2桁}{番号6桁}"
    # 令和年号 = 年 - 2018 (令和元年は2019-2018=1)
    # 実際: 2020 - 2018 = 2 → "02" → "5" + "02" + "060350" = "502060350" ✓

    if len(publi_num) < 13:
        return ""

    try:
        # フォーマット: "01" + "0" + year_4digit + number_6digit (計13桁)
        # 例: "0102020060350" → year=2020, number="060350"
        year = int(publi_num[3:7])    # 位置3-6: "2020"
        number_6 = publi_num[7:]      # 位置7-12: "060350" (6桁)

        # 令和年号 (令和元年=2019, 令和2年=2020, ...)
        reiwa_year = year - 2018
        jpa_key = f"JPA 5{reiwa_year:02d}{number_6}"
        return jpa_key
    except Exception:
        return ""


def _call_api_sync(page, endpoint: str, payload: dict) -> dict:
    """ページのコンテキストから API を呼び出す・同期版 (Cookie / セッションを引き継ぐ)。"""
    try:
        result = page.evaluate(f"""
            async () => {{
                const serviceId = '{endpoint.split("/")[-1].upper()}';
                try {{
                    await fetch('/app/docgw/wsc1101', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{"SERVICE_ID": serviceId}})
                    }});
                }} catch(e) {{}}

                const r = await fetch('{endpoint}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({json.dumps(payload, ensure_ascii=False)})
                }});
                return await r.json();
            }}
        """)
        return result or {}
    except Exception as e:
        logger.error(f"API 呼び出しエラー {endpoint}: {e}")
        return {}


def _parse_figures(gazette_data: dict, hash_value: str) -> list[PatentFigure]:
    """wsp3101 のレスポンスから図面 URL リストを生成する。"""
    figures = []
    if not gazette_data:
        return figures

    try:
        links = gazette_data.get("LINK", [])
        for link in links:
            url_path = link.get("LINK_URL", "")
            if url_path and hash_value in url_path:
                link_cd = link.get("LINK_CD", "")
                full_url = f"https://www.j-platpat.inpit.go.jp{url_path}"
                figures.append(PatentFigure(
                    figure_number=link_cd,
                    url=full_url,
                    description="",
                ))
    except Exception as e:
        logger.warning(f"図面パースエラー: {e}")

    return figures


# ========== Phase 2 用スタブ (将来実装) ==========

async def search_patents(
    search_query: str,
    max_results: int = 100,
) -> list[dict]:
    """検索式による特許一括検索 (Phase 2 で実装)。

    Args:
        search_query: FI コード、キーワード等を含む検索式
        max_results: 最大取得件数

    Returns:
        メタデータ + 要約のみのリスト
    """
    raise NotImplementedError("Phase 2 で実装予定です。")
