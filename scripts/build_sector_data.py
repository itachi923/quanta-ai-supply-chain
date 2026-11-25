import urllib.request
import json
import time
import os

STOCKS_CONFIG = [
    {
        "id": "2382",
        "name": "廣達",
        "fullName": "廣達電腦股份有限公司",
        "category": "odm",
        "categoryName": "AI伺服器/ODM代工",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": True,
        "leaderWhy": "單季合併營收衝破 1.1 兆元，NVIDIA GB200 NVL72 首發戰略代工廠，微軟、Google、AWS、Meta 四大 CSP 白牌直供市占全球第一。",
        "leaderRole": "全球AI伺服器代工龍頭 · 兆元權值旗艦",
        "description": "創立於1988年，全球最大筆記型電腦研發製造廠，亦為全球最大雲端資料中心與AI伺服器ODM直供商。深度攜手NVIDIA首發GB200 NVL72整機櫃，直供微軟、Google、AWS、Meta。",
        "mainProducts": "AI伺服器整機櫃(55%)、筆記型電腦(32%)、車用電子ECU(9%)、智慧醫療與邊緣運算(4%)",
        "upstream": "半導體晶圓(台積電)、運算晶片(NVIDIA/AMD)、水冷模組(奇鋐/雙鴻)、重型導軌(川湖)、電源(台達電/光寶科)、PCB(台光電/金像電)",
        "downstream": "超大規模雲端服務商(微軟Azure、Google Cloud、AWS、Meta)、筆電品牌(Apple MacBook)、電動車廠(Tesla)",
        "financials": {
            "trailingEPS": 25.76,
            "q3Revenue": "1.11 兆元",
            "grossMargin": "8.7%",
            "operatingMargin": "5.2%",
            "roe": "27.6%",
            "dividendYield": "3.8%"
        }
    },
    {
        "id": "6669",
        "name": "緯穎",
        "fullName": "緯穎科技服務股份有限公司",
        "category": "odm",
        "categoryName": "白牌雲端伺服器",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "純度最高白牌伺服器股王 · 千金高價股",
        "description": "緯創集團旗下子公司，專注於超大型雲端資料中心客製化白牌伺服器(ODM Direct)。客戶結構集中於Meta、微軟、AWS，長年投入液冷與先進浸沒式冷卻技術，無消費性電子負擔。",
        "mainProducts": "雲端伺服器系統(90%+)、超高密度儲存伺服器、水冷運算機架",
        "upstream": "運算處理器(Intel/AMD/NVIDIA)、伺服器散熱模組(奇鋐/雙鴻)、重型導軌(川湖)、伺服器機殼(勤誠)、高階載板(台光電)",
        "downstream": "超大規模雲端資料中心(Meta、微軟Azure、亞馬遜AWS)",
        "financials": {
            "trailingEPS": 118.5,
            "q3Revenue": "970 億元",
            "grossMargin": "10.8%",
            "operatingMargin": "7.9%",
            "roe": "34.2%",
            "dividendYield": "3.2%"
        }
    },
    {
        "id": "3231",
        "name": "緯創",
        "fullName": "緯創資通股份有限公司",
        "category": "odm",
        "categoryName": "AI伺服器基板代工",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "NVIDIA GPU 運算基板獨家/主力製造商",
        "description": "全球領先的電子代工大廠，近年大舉處分iPhone組裝廠，全面轉型進軍AI伺服器。掌握技術門檻最高的NVIDIA GPU基板(Baseboard/OAM)，為全球AI算力不可或缺的基石。",
        "mainProducts": "GPU運算加速基板與AI伺服器主機板(45%)、筆電與PC代工(35%)、工業與物聯網(12%)、其他(8%)",
        "upstream": "台積電先進封裝晶片(CoWoS)、高階銅箔基板(台光電)、伺服器電源(光寶科)、高多層PCB板(金像電)",
        "downstream": "伺服器系統廠(Dell、HP、廣達)、雲端服務供應商(微軟、AWS、Google)",
        "financials": {
            "trailingEPS": 6.85,
            "q3Revenue": "2,725 億元",
            "grossMargin": "8.3%",
            "operatingMargin": "4.4%",
            "roe": "18.5%",
            "dividendYield": "3.5%"
        }
    },
    {
        "id": "2356",
        "name": "英業達",
        "fullName": "英業達股份有限公司",
        "category": "odm",
        "categoryName": "伺服器主機板/筆電",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "伺服器主機板 (L6) 出貨全球霸主",
        "description": "台灣老牌電子代工五哥之一，在伺服器主機板(L6)出貨量長期稱冠全球。同時兼具商用筆記型電腦組裝，並積極跨入自研AI加速晶片(VectorMesh)與邊緣AI解決方案。",
        "mainProducts": "伺服器主機板與準系統(42%)、筆記型電腦(50%)、智慧裝置與車載(8%)",
        "upstream": "中央處理器(Intel/AMD)、伺服器散熱模組、記憶體模組、高階PCB板",
        "downstream": "Google Cloud、微軟、北美CSP、全球PC品牌大廠(HP、Dell)",
        "financials": {
            "trailingEPS": 2.15,
            "q3Revenue": "1,638 億元",
            "grossMargin": "5.3%",
            "operatingMargin": "1.7%",
            "roe": "11.2%",
            "dividendYield": "4.0%"
        }
    },
    {
        "id": "2376",
        "name": "技嘉",
        "fullName": "技嘉科技股份有限公司",
        "category": "odm",
        "categoryName": "AI伺服器/板卡準系統",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "企業端與二線CSP AI伺服器爆發黑馬",
        "description": "早期以主機板與顯示卡聞名，近年藉由子公司技鋼科技(Giga Computing)大展身手。以極高客製化彈性與熱管理技術，快速滿足歐美二線Tier-2 CSP、科研機構及企業生成式AI私有雲訂單。",
        "mainProducts": "AI與高效能伺服器(55%)、顯示卡與主機板(35%)、電競周邊與筆電(10%)",
        "upstream": "GPU圖形晶片(NVIDIA/AMD)、記憶體顆粒、高階散熱風扇與水冷板、PCB載板",
        "downstream": "歐美Tier-2雲端服務商(CoreWeave、Lambda)、國家超級電腦中心、各國大型企業私有雲",
        "financials": {
            "trailingEPS": 15.2,
            "q3Revenue": "704 億元",
            "grossMargin": "11.1%",
            "operatingMargin": "5.1%",
            "roe": "23.4%",
            "dividendYield": "3.3%"
        }
    },
    {
        "id": "2357",
        "name": "華碩",
        "fullName": "華碩電腦股份有限公司",
        "category": "brand_pc",
        "categoryName": "PC品牌/AI伺服器",
        "subGroup": "brand_pc",
        "subGroupName": "電腦品牌與電競旗艦",
        "groupBadge": "全球終端品牌",
        "isLeader": True,
        "leaderWhy": "全球主機板與電競 ROG 第一品牌，近四季 EPS 高達 42.5 元，手握國家級 AI 超級電腦大型伺服器標案，跨界展現強大系統實力。",
        "leaderRole": "全球主機板與電競PC龍頭 · 積極搶攻AI超級電腦",
        "description": "全球主機板第一品牌、全球前三大消費性筆電廠。旗下ROG品牌穩坐全球電競第一把交椅。近年成立伺服器事業群，獲得國家級AI超級電腦與企業級伺服器大單，目標伺服器營收翻倍成長。",
        "mainProducts": "電腦系統(筆電/桌機/電競)(60%)、主機板與顯示卡(30%)、AI伺服器與AIoT(10%)",
        "upstream": "CPU/GPU晶片(Intel/AMD/NVIDIA)、面板(友達/群創)、PCB與被動元件、記憶體",
        "downstream": "全球消費性與商用終端用戶、3C經銷通路、企業資料中心與國家算力中心",
        "financials": {
            "trailingEPS": 42.5,
            "q3Revenue": "1,665 億元",
            "grossMargin": "17.2%",
            "operatingMargin": "7.8%",
            "roe": "16.8%",
            "dividendYield": "3.6%"
        }
    },
    {
        "id": "2377",
        "name": "微星",
        "fullName": "微星科技股份有限公司",
        "category": "brand_pc",
        "categoryName": "電競筆電/主機板",
        "subGroup": "brand_pc",
        "subGroupName": "電腦品牌與電競旗艦",
        "groupBadge": "全球終端品牌",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "全球高階電競硬體與創作者筆電先鋒",
        "description": "全球知名的電競筆電、主機板與顯示卡品牌廠。近年以深厚的高頻電路與散熱底蘊，拓展伺服器、邊緣運算、工控電腦及車載充電樁市場。",
        "mainProducts": "電競筆記型電腦與桌機(48%)、顯示卡與主機板(38%)、伺服器與工控周邊(14%)",
        "upstream": "NVIDIA GPU、Intel/AMD CPU、電競面板、PCB高頻板、高速風扇與均熱板",
        "downstream": "全球電競玩家、內容創作者、電競賽事組織、企業專業工作站客戶",
        "financials": {
            "trailingEPS": 12.3,
            "q3Revenue": "520 億元",
            "grossMargin": "12.5%",
            "operatingMargin": "4.2%",
            "roe": "14.5%",
            "dividendYield": "4.1%"
        }
    },
    {
        "id": "2059",
        "name": "川湖",
        "fullName": "川湖科技股份有限公司",
        "category": "components",
        "categoryName": "伺服器專利導軌",
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": True,
        "leaderWhy": "手握全球逾 3,000 項專利，毛利率高達 68.2% 冠絕台股硬體族群，全球唯一量產通過 GB200 1.3 噸抗震認證之重型導軌獨占龍頭。",
        "leaderRole": "全球伺服器導軌獨占霸主 · 毛利近七成千金股",
        "description": "全球伺服器重型鋼珠滑軌龍頭，全球伺服器市占超過50%，AI伺服器更達80%以上。坐擁逾3,000項全球專利壁壘。面對GB200重達1.3噸的機櫃耐重抗震考驗，為全球唯一成熟量產者。",
        "mainProducts": "伺服器重型滑軌(75%)、高級廚具鉸鏈導軌(20%)、其他精密機構件(5%)",
        "upstream": "特殊高拉力鋼材、精密鋼珠、潤滑阻尼材料",
        "downstream": "伺服器代工廠(廣達、鴻海、緯創、緯穎)、直供北美CSP機櫃",
        "financials": {
            "trailingEPS": 62.8,
            "q3Revenue": "28.5 億元",
            "grossMargin": "68.2%",
            "operatingMargin": "57.1%",
            "roe": "29.8%",
            "dividendYield": "2.8%"
        }
    },
    {
        "id": "3017",
        "name": "奇鋐",
        "fullName": "奇鋐科技股份有限公司",
        "category": "components",
        "categoryName": "伺服器水冷散熱",
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": True,
        "leaderWhy": "水冷板、分流管 (Manifold)、CDU 冷卻分配單元一條龍全自製，通過 NVIDIA 官方嚴苛驗證，伺服器散熱營收規模與水冷出貨居台廠第一。",
        "leaderRole": "AI伺服器水冷散熱系統一條龍總冠軍",
        "description": "全球散熱解決方案巨擘。針對AI伺服器晶片超過1000W之高熱量，奇鋐成功開發水冷板(Cold Plate)、分流管(Manifold)、冷卻分配單元(CDU)，具備全套一條龍自製能力，通過NVIDIA認證。",
        "mainProducts": "伺服器水冷板與CDU(50%)、散熱模組與風扇(35%)、機箱與系統組裝(15%)",
        "upstream": "銅/鋁散熱金屬材料、微型高壓水泵浦、特殊冷卻液與快接接頭",
        "downstream": "直供廣達、鴻海、微軟、亞馬遜等AI伺服器與資料中心組裝廠",
        "financials": {
            "trailingEPS": 22.4,
            "q3Revenue": "191 億元",
            "grossMargin": "24.2%",
            "operatingMargin": "13.8%",
            "roe": "26.5%",
            "dividendYield": "2.5%"
        }
    },
    {
        "id": "3324",
        "name": "雙鴻",
        "fullName": "雙鴻科技股份有限公司",
        "category": "components",
        "categoryName": "水冷板/散熱模組",
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "液冷散熱模組核心指標大廠",
        "description": "台灣散熱技術先驅，產品跨足筆電、顯示卡、車用及AI伺服器。在水冷板與機櫃級散熱迴路布局成熟，為輝達伺服器供應鏈水冷主要供應商之一。",
        "mainProducts": "伺服器水冷與熱導管(48%)、筆電散熱模組(32%)、顯示卡與車用散熱(20%)",
        "upstream": "純銅管、鋁鰭片、微通道散熱金屬板、導熱膏與冷卻液",
        "downstream": "伺服器ODM(緯創、廣達、緯穎)、筆電大廠、國際顯示卡廠",
        "financials": {
            "trailingEPS": 20.8,
            "q3Revenue": "43.2 億元",
            "grossMargin": "26.8%",
            "operatingMargin": "12.5%",
            "roe": "24.1%",
            "dividendYield": "2.4%"
        }
    },
    {
        "id": "8210",
        "name": "勤誠",
        "fullName": "勤誠興業股份有限公司",
        "category": "components",
        "categoryName": "伺服器機殼霸主",
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "全球雲端伺服器機殼與機構件龍頭",
        "description": "專注於伺服器機殼研發與製造逾40年，全球伺服器機殼市占率第一。從1U/2U/4U標準機箱到GB200龐大的整機櫃機構件，為北美CSP客製化機箱的首選合作夥伴。",
        "mainProducts": "伺服器機殼(90%+)、伺服器機構組件、機架配件",
        "upstream": "冷軋鋼板、電鍍鍍鋅鋼板、沖壓模具、各類機構緊固件",
        "downstream": "白牌伺服器代工廠(廣達、英業達、緯穎)、直供北美CSP與系統整合商",
        "financials": {
            "trailingEPS": 14.5,
            "q3Revenue": "42.8 億元",
            "grossMargin": "25.6%",
            "operatingMargin": "15.2%",
            "roe": "28.1%",
            "dividendYield": "3.1%"
        }
    },
    {
        "id": "2395",
        "name": "研華",
        "fullName": "研華股份有限公司",
        "category": "ipc_iot",
        "categoryName": "工業電腦IPC龍頭",
        "subGroup": "ipc_iot",
        "subGroupName": "工業電腦與邊緣物聯網",
        "groupBadge": "工業AI與自動化",
        "isLeader": True,
        "leaderWhy": "全球工業電腦 (IPC) 市占率逾 35% 稱霸全球超過二十年，毛利率長年穩健維持 40% 以上，為全球智慧工廠與邊緣 AI 推論標準制定者。",
        "leaderRole": "全球工業電腦第一品牌 · 工業物聯網霸主",
        "description": "創立於1983年，全球工業電腦(IPC)市占率超過35%，長年穩居全球第一。產品廣泛應用於智慧工廠、醫療設備、軌道交通、機器人控制器及邊緣AI推論運算。",
        "mainProducts": "工業物聯網系統(46%)、嵌入式板卡與運算核心(38%)、應用電腦與智慧醫療(16%)",
        "upstream": "工規級CPU/晶片組(Intel/AMD/ARM)、高可靠度PCB、工業級記憶體",
        "downstream": "全球工業自動化大廠(西門子、ABB)、智慧醫療院所、半導體設備商、零售物聯網",
        "financials": {
            "trailingEPS": 11.2,
            "q3Revenue": "150 億元",
            "grossMargin": "40.5%",
            "operatingMargin": "16.8%",
            "roe": "20.2%",
            "dividendYield": "3.2%"
        }
    },
    {
        "id": "6414",
        "name": "樺漢",
        "fullName": "樺漢科技股份有限公司",
        "category": "ipc_iot",
        "categoryName": "工控系統/邊緣運算",
        "subGroup": "ipc_iot",
        "subGroupName": "工業電腦與邊緣物聯網",
        "groupBadge": "工業AI與自動化",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "鴻海集團工業物聯網旗艦 · 軟硬整合",
        "description": "鴻海集團旗下工業電腦大廠，透過併購歐洲S&T/Kontron具備軟體、韌體與雲端SaaS能力。深度切入智慧零售、智慧工廠、半導體ESG節能監控及邊緣AI機器人領域。",
        "mainProducts": "工業物聯網系統軟硬體(55%)、智慧家庭與安全控制(30%)、雲端系統整合(15%)",
        "upstream": "鴻海集團機構件與組裝資源、工業晶片、網路通訊模組",
        "downstream": "歐美智慧軌道交通、半導體晶圓廠、全球智慧零售自助結帳終端",
        "financials": {
            "trailingEPS": 19.5,
            "q3Revenue": "377 億元",
            "grossMargin": "19.8%",
            "operatingMargin": "5.6%",
            "roe": "17.4%",
            "dividendYield": "3.9%"
        }
    },
    {
        "id": "3706",
        "name": "神達",
        "fullName": "神達控股股份有限公司",
        "category": "odm",
        "categoryName": "伺服器/車載電子",
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "承接英特爾DSG伺服器業務 · 智慧移動",
        "description": "聯華神通集團成員，旗下神雲科技(MiTAC)於2023年承接Intel資料中心解決方案群(DSG)伺服器業務，在企業伺服器與AI運算大幅成長；神達數位則深耕行車紀錄器與車用導航。",
        "mainProducts": "雲端伺服器與邊緣運算(80%)、車載電子與智慧行車(20%)",
        "upstream": "Intel/AMD運算處理器、記憶體、主機板被動元件、車用感測鏡頭",
        "downstream": "全球企業資料中心、雲端服務商、一線車廠與一般消費大眾",
        "financials": {
            "trailingEPS": 3.85,
            "q3Revenue": "151 億元",
            "grossMargin": "12.8%",
            "operatingMargin": "4.1%",
            "roe": "9.5%",
            "dividendYield": "3.7%"
        }
    },
    {
        "id": "2352",
        "name": "佳世達",
        "fullName": "佳世達科技股份有限公司",
        "category": "brand_pc",
        "categoryName": "顯示器/智慧醫療",
        "subGroup": "peripherals",
        "subGroupName": "週邊設備與智慧顯示",
        "groupBadge": "視覺聲學與光學",
        "isLeader": False,
        "leaderWhy": "",
        "leaderRole": "顯示技術先驅 · 大艦隊智慧醫療佈局",
        "description": "明基佳世達集團核心旗艦，為全球液晶顯示器與投影機領導製造商。近年推動「價值轉型大艦隊」，高附加價值事業涵蓋智慧醫療(明基醫院)、智慧解決方案及網通事業。",
        "mainProducts": "顯示器與商業設備(50%)、醫療器材與醫療服務(25%)、智慧解決方案與網通(25%)",
        "upstream": "液晶面板(友達)、光學零組件、驅動IC、機構件",
        "downstream": "全球醫療院所、企業商用展示會議、終端消費者",
        "financials": {
            "trailingEPS": 2.1,
            "q3Revenue": "508 億元",
            "grossMargin": "16.5%",
            "operatingMargin": "2.8%",
            "roe": "6.8%",
            "dividendYield": "4.5%"
        }
    },
    {
        "id": "4915",
        "name": "致伸",
        "fullName": "致伸科技股份有限公司",
        "category": "peripherals",
        "categoryName": "電腦週邊/光學感測",
        "subGroup": "peripherals",
        "subGroupName": "週邊設備與智慧顯示",
        "groupBadge": "視覺聲學與光學",
        "isLeader": True,
        "leaderWhy": "電腦高階週邊、車載 ADAS 鏡頭模組與頂級電競聲學領導大廠，高附加價值產品比重攀升，兼具穩定高殖利率。",
        "leaderRole": "視覺影像與聲學感測週邊領導廠",
        "description": "跨足電腦週邊、智慧行動影像與頂級聲學領域。提供高階滑鼠鍵盤、車載ADAS鏡頭相機模組、智慧安全監控及專業耳機聲學設備，持續提升高毛利車用與工業應用比重。",
        "mainProducts": "資訊週邊設備(40%)、智慧生活與聲學(35%)、車載與工業安全影像(25%)",
        "upstream": "CMOS影像感測器、聲學單體、精密微型馬達、光學鏡片",
        "downstream": "一線PC週邊品牌(羅技等)、歐美電動車廠、智慧音訊品牌",
        "financials": {
            "trailingEPS": 5.85,
            "q3Revenue": "160 億元",
            "grossMargin": "16.8%",
            "operatingMargin": "4.6%",
            "roe": "14.2%",
            "dividendYield": "5.2%"
        }
    }
]

def build_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_path = os.path.join(base_dir, 'data', 'sector_stocks.json')
    os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)

    print("Fetching live prices for all 16 sector stocks...")
    for s in STOCKS_CONFIG:
        sid = s["id"]
        try:
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={sid}&start_date=2026-08-01"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8')).get('data', [])
                if data:
                    s["history"] = data[-60:] # keep recent 60 trading days for interactive chart
                    latest = data[-1]
                    prev = data[-2] if len(data) > 1 else data[-1]
                    s["price"] = latest["close"]
                    s["spread"] = latest["spread"]
                    prev_close = prev["close"]
                    s["pct"] = round((latest["spread"] / prev_close) * 100, 2) if prev_close else 0.0
                    s["volume"] = round(latest["Trading_Volume"] / 1000)
                    s["date"] = latest["date"]
                    print(f"[{sid}] {s['name']}: {s['price']} (Spread: {s['spread']}, {s['pct']}%)")
                else:
                    print(f"[{sid}] No data")
        except Exception as e:
            print(f"Error {sid}: {e}")
        time.sleep(0.1)

    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(STOCKS_CONFIG, f, ensure_ascii=False, indent=2)

    print(f"Successfully wrote {len(STOCKS_CONFIG)} stocks to {target_path}")

if __name__ == '__main__':
    build_data()
