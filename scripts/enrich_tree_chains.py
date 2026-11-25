import json
import os

TREE_CHAINS = {
    "2382": {
        "title": "廣達 (2382) AI 伺服器與雲端產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "核心運算晶片", "icon": "🧠" },
            { "id": "ub2", "name": "水冷散熱系統", "icon": "❄️" },
            { "id": "ub3", "name": "重型導軌機殼", "icon": "🗄️" },
            { "id": "ub4", "name": "高階PCB與電源", "icon": "🧬" }
        ],
        "upstreamLeaves": [
            { "name": "台積電 (2330)", "role": "晶圓代工/CoWoS", "branch": "ub1", "icon": "🏭", "color": "#0369a1" },
            { "name": "輝達 (NVIDIA)", "role": "GPU 算力晶片核心", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "奇鋐 (3017)", "role": "水冷板/CDU一條龍", "branch": "ub2", "icon": "❄️", "color": "#0284c7" },
            { "name": "雙鴻 (3324)", "role": "散熱迴路與水冷板", "branch": "ub2", "icon": "💧", "color": "#0284c7" },
            { "name": "川湖 (2059)", "role": "專利重型伺服器導軌", "branch": "ub3", "icon": "👑", "color": "#d97706" },
            { "name": "勤誠 (8210)", "role": "伺服器機殼霸主", "branch": "ub3", "icon": "📦", "color": "#0284c7" },
            { "name": "台光電 (2383)", "role": "超高階銅箔基板", "branch": "ub4", "icon": "🧬", "color": "#0284c7" },
            { "name": "台達電 (2308)", "role": "伺服器高壓電源", "branch": "ub4", "icon": "🔋", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "超大規模雲端 CSP", "icon": "☁️" },
            { "id": "db2", "name": "品牌電腦與智慧移動", "icon": "💻" }
        ],
        "downstreamLeaves": [
            { "name": "微軟 (Azure)", "role": "OpenAI 算力大本營", "branch": "db1", "icon": "☁️", "color": "#0f766e" },
            { "name": "Google", "role": "Gemini 與自研 TPU", "branch": "db1", "icon": "🔍", "color": "#0f766e" },
            { "name": "亞馬遜 AWS", "role": "全球雲端市占第一", "branch": "db1", "icon": "📦", "color": "#0f766e" },
            { "name": "Meta (臉書)", "role": "Llama 開源大模型", "branch": "db1", "icon": "👥", "color": "#0f766e" },
            { "name": "蘋果 (Apple)", "role": "MacBook 筆電主力", "branch": "db2", "icon": "🍎", "color": "#0f766e" },
            { "name": "特斯拉 (Tesla)", "role": "車載中控電腦 ECU", "branch": "db2", "icon": "🚗", "color": "#0f766e" }
        ]
    },
    "6669": {
        "title": "緯穎 (6669) 純白牌雲端伺服器直供產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "運算核心處理器", "icon": "🧠" },
            { "id": "ub2", "name": "先進液冷與散熱", "icon": "❄️" },
            { "id": "ub3", "name": "專利導軌與機箱", "icon": "🗄️" },
            { "id": "ub4", "name": "低損耗高速電路板", "icon": "🧬" }
        ],
        "upstreamLeaves": [
            { "name": "輝達 (NVIDIA)", "role": "GB200 / H100 晶片", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "超微 (AMD)", "role": "EPYC 雲端 CPU", "branch": "ub1", "icon": "💻", "color": "#0369a1" },
            { "name": "奇鋐 (3017)", "role": "水冷板/CDU分流管", "branch": "ub2", "icon": "❄️", "color": "#0284c7" },
            { "name": "雙鴻 (3324)", "role": "微通道水冷板", "branch": "ub2", "icon": "💧", "color": "#0284c7" },
            { "name": "川湖 (2059)", "role": "高承重伺服器滑軌", "branch": "ub3", "icon": "👑", "color": "#d97706" },
            { "name": "勤誠 (8210)", "role": "資料中心客製機箱", "branch": "ub3", "icon": "📦", "color": "#0284c7" },
            { "name": "台光電 (2383)", "role": "極低耗損高頻 CCL", "branch": "ub4", "icon": "🧬", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "超大規模雲端 CSP", "icon": "☁️" }
        ],
        "downstreamLeaves": [
            { "name": "Meta (最大客戶)", "role": "貢獻營收逾五成", "branch": "db1", "icon": "👥", "color": "#0f766e" },
            { "name": "微軟 (Azure)", "role": "大型生成式 AI 機房", "branch": "db1", "icon": "☁️", "color": "#0f766e" },
            { "name": "亞馬遜 (AWS)", "role": "ASIC 與 GPU 雲架構", "branch": "db1", "icon": "📦", "color": "#0f766e" }
        ]
    },
    "3231": {
        "title": "緯創 (3231) GPU 運算基板與代工產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "先進封裝與晶圓代工", "icon": "🏭" },
            { "id": "ub2", "name": "高階銅箔基板與PCB", "icon": "🧬" },
            { "id": "ub3", "name": "伺服器高瓦數電源", "icon": "⚡" }
        ],
        "upstreamLeaves": [
            { "name": "台積電 (2330)", "role": "CoWoS 3D 封裝", "branch": "ub1", "icon": "🏭", "color": "#0369a1" },
            { "name": "輝達 (NVIDIA)", "role": "原廠加速核心模組", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "台光電 (2383)", "role": "高頻高速銅箔基板", "branch": "ub2", "icon": "🧬", "color": "#0284c7" },
            { "name": "金像電 (2368)", "role": "多層伺服器載板", "branch": "ub2", "icon": "🎛️", "color": "#0284c7" },
            { "name": "光寶科 (2301)", "role": "高效率電源機箱", "branch": "ub3", "icon": "⚡", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "國際伺服器系統代工", "icon": "🖥️" },
            { "id": "db2", "name": "北美頂級雲端 CSP", "icon": "☁️" }
        ],
        "downstreamLeaves": [
            { "name": "戴爾 (Dell)", "role": "企業級 AI 伺服器", "branch": "db1", "icon": "💻", "color": "#0f766e" },
            { "name": "惠普 (HP Enterprise)", "role": "HPE 資料中心", "branch": "db1", "icon": "🖥️", "color": "#0f766e" },
            { "name": "廣達電腦", "role": "採購基板組裝整機", "branch": "db1", "icon": "🤖", "color": "#2563eb" },
            { "name": "北美頂級 CSP", "role": "直供直簽運算基板", "branch": "db2", "icon": "☁️", "color": "#0f766e" }
        ]
    },
    "2357": {
        "title": "華碩 (2357) 主機板、筆電與 AI 超級電腦產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "核心運算處理晶片", "icon": "🧠" },
            { "id": "ub2", "name": "顯示面板與儲存", "icon": "🖥️" },
            { "id": "ub3", "name": "高階PCB與網通晶片", "icon": "📶" }
        ],
        "upstreamLeaves": [
            { "name": "輝達 (NVIDIA)", "role": "GeForce / AI GPU", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "英特爾 (Intel)", "role": "Core / Xeon 處理器", "branch": "ub1", "icon": "💻", "color": "#0369a1" },
            { "name": "超微 (AMD)", "role": "Ryzen / EPYC", "branch": "ub1", "icon": "🔥", "color": "#0369a1" },
            { "name": "友達光電 (2409)", "role": "OLED / 電競高刷螢幕", "branch": "ub2", "icon": "🖥️", "color": "#0284c7" },
            { "name": "聯發科 (2454)", "role": "Wi-Fi 7 / 網通晶片", "branch": "ub3", "icon": "📶", "color": "#0284c7" },
            { "name": "欣興 (3037)", "role": "高階 ABF 載板", "branch": "ub3", "icon": "🧬", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "電競玩家與消費大眾", "icon": "🎮" },
            { "id": "db2", "name": "企業私有雲與國家算力", "icon": "🏛️" }
        ],
        "downstreamLeaves": [
            { "name": "ROG 電競玩家", "role": "全球電競筆電第一品牌", "branch": "db1", "icon": "🎮", "color": "#0f766e" },
            { "name": "全球 3C 經銷通路", "role": "國際實體與電商通路", "branch": "db1", "icon": "🛒", "color": "#0f766e" },
            { "name": "國網中心 (NCHC)", "role": "國家級 AI 超級電腦", "branch": "db2", "icon": "🏛️", "color": "#0f766e" },
            { "name": "台智雲 (TWS)", "role": "企業生成式 AI 大模型", "branch": "db2", "icon": "☁️", "color": "#0f766e" }
        ]
    },
    "2059": {
        "title": "川湖 (2059) 伺服器重型專利導軌產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "高強度特種鋼材", "icon": "🔩" },
            { "id": "ub2", "name": "精密微型鋼珠滾件", "icon": "⚙️" },
            { "id": "ub3", "name": "特殊阻尼耐磨材料", "icon": "🧪" }
        ],
        "upstreamLeaves": [
            { "name": "中鋼與特鋼廠", "role": "高拉力航太冷軋鋼", "branch": "ub1", "icon": "🔩", "color": "#0369a1" },
            { "name": "精密微型鋼珠廠", "role": "高耐重微型軸承", "branch": "ub2", "icon": "⚙️", "color": "#0284c7" },
            { "name": "高分子阻尼材料", "role": "防震靜音回彈模組", "branch": "ub3", "icon": "🧪", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "伺服器系統代工 (ODM)", "icon": "🤖" },
            { "id": "db2", "name": "雲端機櫃與高端家具", "icon": "☁️" }
        ],
        "downstreamLeaves": [
            { "name": "廣達電腦 (2382)", "role": "GB200 機櫃滑軌直供", "branch": "db1", "icon": "🤖", "color": "#2563eb" },
            { "name": "鴻海集團 (2317)", "role": "代工組裝滑軌主力", "branch": "db1", "icon": "🦊", "color": "#2563eb" },
            { "name": "緯穎科技 (6669)", "role": "白牌雲端直供機櫃導軌", "branch": "db1", "icon": "☁️", "color": "#2563eb" },
            { "name": "微軟 / Google 機架", "role": "1.3噸耐震認證機架", "branch": "db2", "icon": "☁️", "color": "#0f766e" },
            { "name": "歐美奢華廚具精品", "role": "頂級櫥櫃緩衝滑軌", "branch": "db2", "icon": "🍳", "color": "#0f766e" }
        ]
    },
    "3017": {
        "title": "奇鋐 (3017) 伺服器水冷散熱產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "高導熱金屬原材料", "icon": "🪙" },
            { "id": "ub2", "name": "流體動力微型泵浦", "icon": "💧" },
            { "id": "ub3", "name": "風扇驅動與快接頭", "icon": "🔌" }
        ],
        "upstreamLeaves": [
            { "name": "特種無氧銅與鋁合金", "role": "微通道散熱底座", "branch": "ub1", "icon": "🪙", "color": "#0369a1" },
            { "name": "微型磁驅高壓泵浦", "role": "液冷迴路循環核心", "branch": "ub2", "icon": "💧", "color": "#0284c7" },
            { "name": "風扇驅動控制 IC", "role": "精準溫控轉速晶片", "branch": "ub3", "icon": "⚡", "color": "#0284c7" },
            { "name": "航太級無漏快接頭", "role": "高壓防蝕快拆閥", "branch": "ub3", "icon": "🔌", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "AI 伺服器代工系統廠", "icon": "🤖" },
            { "id": "db2", "name": "超大型雲端資料中心", "icon": "☁️" }
        ],
        "downstreamLeaves": [
            { "name": "廣達電腦 (2382)", "role": "GB200 水冷板大宗供貨", "branch": "db1", "icon": "🤖", "color": "#2563eb" },
            { "name": "鴻海科技 (2317)", "role": "NVL72 機櫃冷卻系統", "branch": "db1", "icon": "🦊", "color": "#2563eb" },
            { "name": "美超微 (Supermicro)", "role": "液冷伺服器整機出貨", "branch": "db1", "icon": "🖥️", "color": "#0f766e" },
            { "name": "微軟 / AWS 機房", "role": "解決 1000W+ 散熱瓶頸", "branch": "db2", "icon": "☁️", "color": "#0f766e" }
        ]
    },
    "3324": {
        "title": "雙鴻 (3324) 水冷板與散熱模組產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "高導熱純銅管與均熱板", "icon": "🪙" },
            { "id": "ub2", "name": "微通道蝕刻冷卻材料", "icon": "💧" },
            { "id": "ub3", "name": "高效散熱矽脂與導熱膏", "icon": "🧪" }
        ],
        "upstreamLeaves": [
            { "name": "高純度電解無氧銅", "role": "超薄熱導管與均熱片", "branch": "ub1", "icon": "🪙", "color": "#0369a1" },
            { "name": "雷射雕刻微通道板", "role": "精密水冷通道基板", "branch": "ub2", "icon": "💧", "color": "#0284c7" },
            { "name": "高導熱散熱膏介質", "role": "晶片接面導熱介質", "branch": "ub3", "icon": "🧪", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "伺服器代工與雲端供應", "icon": "☁️" },
            { "id": "db2", "name": "電競筆電與車載散熱", "icon": "💻" }
        ],
        "downstreamLeaves": [
            { "name": "緯創資通 (3231)", "role": "GPU 運算基板散熱", "branch": "db1", "icon": "🧩", "color": "#2563eb" },
            { "name": "緯穎科技 (6669)", "role": "水冷冷卻分配系統", "branch": "db1", "icon": "☁️", "color": "#2563eb" },
            { "name": "華碩 / 微星", "role": "電競旗艦顯示卡散熱", "branch": "db2", "icon": "🎮", "color": "#0f766e" },
            { "name": "歐美一線電動車廠", "role": "車載智慧座艙水冷", "branch": "db2", "icon": "🚗", "color": "#0f766e" }
        ]
    },
    "8210": {
        "title": "勤誠 (8210) 伺服器機殼與機構件產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "防鏽鍍鋅鋼板材料", "icon": "🔩" },
            { "id": "ub2", "name": "沖壓模具與精密緊固件", "icon": "⚙️" },
            { "id": "ub3", "name": "電磁屏蔽抗干擾組件", "icon": "🛡️" }
        ],
        "upstreamLeaves": [
            { "name": "中鋼與鍍鋅鋼廠", "role": "抗震防腐冷軋鋼板", "branch": "ub1", "icon": "🔩", "color": "#0369a1" },
            { "name": "精密沖壓模具開發廠", "role": "高精度沖孔通風網孔", "branch": "ub2", "icon": "⚙️", "color": "#0284c7" },
            { "name": "EMI 電磁防護襯墊", "role": "機架防輻射密封組件", "branch": "ub3", "icon": "🛡️", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "白牌伺服器代工 (ODM)", "icon": "🤖" },
            { "id": "db2", "name": "雲端客戶與系統整合", "icon": "☁️" }
        ],
        "downstreamLeaves": [
            { "name": "廣達電腦 (2382)", "role": "客製 1U~4U / AI 機殼", "branch": "db1", "icon": "🤖", "color": "#2563eb" },
            { "name": "英業達 (2356)", "role": "主機板伺服器專用機箱", "branch": "db1", "icon": "⚡", "color": "#2563eb" },
            { "name": "緯穎科技 (6669)", "role": "白牌雲端伺服器機箱", "branch": "db1", "icon": "☁️", "color": "#2563eb" },
            { "name": "北美頂級 CSP 資料中心", "role": "大規模部署雲端機架", "branch": "db2", "icon": "☁️", "color": "#0f766e" }
        ]
    },
    "2376": {
        "title": "技嘉 (2376) AI 伺服器與主機板產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "AI 加速與中央處理晶片", "icon": "🧠" },
            { "id": "ub2", "name": "高速記憶體顆粒", "icon": "💾" },
            { "id": "ub3", "name": "伺服器散熱與耐久主板", "icon": "❄️" }
        ],
        "upstreamLeaves": [
            { "name": "輝達 (NVIDIA)", "role": "HGX / RTX 算力晶片", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "超微 (AMD)", "role": "Instinct / EPYC 處理器", "branch": "ub1", "icon": "🔥", "color": "#0369a1" },
            { "name": "三星 / 美光", "role": "DDR5 / HBM 高速記憶體", "branch": "ub2", "icon": "💾", "color": "#0284c7" },
            { "name": "奇鋐科技 (3017)", "role": "伺服器水冷板模組", "branch": "ub3", "icon": "❄️", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "歐美二線 CSP 算力雲", "icon": "☁️" },
            { "id": "db2", "name": "國家超級電腦與私有雲", "icon": "🏛️" }
        ],
        "downstreamLeaves": [
            { "name": "CoreWeave", "role": "生成式 AI GPU 雲端租賃", "branch": "db1", "icon": "☁️", "color": "#0f766e" },
            { "name": "Lambda Labs", "role": "AI 開發者專用雲算力", "branch": "db1", "icon": "⚡", "color": "#0f766e" },
            { "name": "歐洲超級電腦中心", "role": "國家級科研高速運算", "branch": "db2", "icon": "🏛️", "color": "#0f766e" },
            { "name": "全球電競與通路客戶", "role": "AORUS 品牌板卡與筆電", "branch": "db2", "icon": "🎮", "color": "#0f766e" }
        ]
    },
    "2356": {
        "title": "英業達 (2356) 伺服器主機板與筆電產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "運算核心 CPU / GPU", "icon": "🧠" },
            { "id": "ub2", "name": "高多層伺服器 PCB", "icon": "🧬" },
            { "id": "ub3", "name": "伺服器高效率電源", "icon": "⚡" }
        ],
        "upstreamLeaves": [
            { "name": "英特爾 (Intel)", "role": "Xeon 伺服器處理器", "branch": "ub1", "icon": "💻", "color": "#0369a1" },
            { "name": "超微 (AMD)", "role": "EPYC 運算晶片", "branch": "ub1", "icon": "🔥", "color": "#0369a1" },
            { "name": "金像電 (2368)", "role": "高多層伺服器主機板", "branch": "ub2", "icon": "🎛️", "color": "#0284c7" },
            { "name": "台達電 (2308)", "role": "伺服器電源模組", "branch": "ub3", "icon": "🔋", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "超大型雲端服務商 (CSP)", "icon": "☁️" },
            { "id": "db2", "name": "國際品牌電腦大廠", "icon": "💻" }
        ],
        "downstreamLeaves": [
            { "name": "Google Cloud", "role": "伺服器主機板主力供應", "branch": "db1", "icon": "🔍", "color": "#0f766e" },
            { "name": "微軟 (Microsoft)", "role": "Azure 伺服器主機板", "branch": "db1", "icon": "☁️", "color": "#0f766e" },
            { "name": "惠普 (HP)", "role": "商用筆電與工作站代工", "branch": "db2", "icon": "💻", "color": "#0f766e" },
            { "name": "聯想 (Lenovo)", "role": "全球伺服器代工大單", "branch": "db2", "icon": "🖥️", "color": "#0f766e" }
        ]
    },
    "2377": {
        "title": "微星 (2377) 電競硬體與邊緣運算產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "電競獨立顯示卡晶片", "icon": "⚡" },
            { "id": "ub2", "name": "電競高刷新螢幕面板", "icon": "🖥️" },
            { "id": "ub3", "name": "均熱板與高風壓散熱", "icon": "❄️" }
        ],
        "upstreamLeaves": [
            { "name": "輝達 (NVIDIA)", "role": "GeForce RTX 遊戲晶片", "branch": "ub1", "icon": "⚡", "color": "#0369a1" },
            { "name": "超微 (AMD)", "role": "Radeon / Ryzen 晶片", "branch": "ub1", "icon": "🔥", "color": "#0369a1" },
            { "name": "友達光電 (2409)", "role": "240Hz+ 電競筆電螢幕", "branch": "ub2", "icon": "🖥️", "color": "#0284c7" },
            { "name": "雙鴻科技 (3324)", "role": "超薄均熱板 (VC)", "branch": "ub3", "icon": "💧", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "全球電競玩家與創作者", "icon": "🎮" },
            { "id": "db2", "name": "工控電腦與充電樁", "icon": "⚡" }
        ],
        "downstreamLeaves": [
            { "name": "全球電競玩家", "role": "MSI 泰坦/龍魂玩家群", "branch": "db1", "icon": "🎮", "color": "#0f766e" },
            { "name": "影音與 3D 創作者", "role": "Creator 創作者工作站", "branch": "db1", "icon": "🎨", "color": "#0f766e" },
            { "name": "工控自動化設備商", "role": "強固型工控主機板", "branch": "db2", "icon": "🏭", "color": "#0f766e" },
            { "name": "北美電動車充電樁", "role": "智慧充電樁控制器", "branch": "db2", "icon": "⚡", "color": "#0f766e" }
        ]
    },
    "2395": {
        "title": "研華 (2395) 全球工業電腦與物聯網產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "工規級寬溫處理晶片", "icon": "🧠" },
            { "id": "ub2", "name": "高可靠度工業記憶體", "icon": "💾" },
            { "id": "ub3", "name": "工業自動化感測通訊", "icon": "📶" }
        ],
        "upstreamLeaves": [
            { "name": "英特爾 (Intel)", "role": "工規長銷週期晶片組", "branch": "ub1", "icon": "💻", "color": "#0369a1" },
            { "name": "安謀 (ARM)", "role": "低功耗邊緣運算核心", "branch": "ub1", "icon": "📱", "color": "#0369a1" },
            { "name": "宜鼎國際 (5289)", "role": "工控專用寬溫記憶體", "branch": "ub2", "icon": "💾", "color": "#0284c7" },
            { "name": "瑞昱 (2379)", "role": "工業以太網控制晶片", "branch": "ub3", "icon": "📶", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "智慧製造與半導體自動化", "icon": "🏭" },
            { "id": "db2", "name": "智慧醫療與交通能源", "icon": "🏥" }
        ],
        "downstreamLeaves": [
            { "name": "西門子 (Siemens)", "role": "工廠自動化控制器", "branch": "db1", "icon": "🏭", "color": "#0f766e" },
            { "name": "台積電等晶圓廠", "role": "晶圓製造設備控制核心", "branch": "db1", "icon": "🔬", "color": "#0f766e" },
            { "name": "歐美智慧醫療院所", "role": "手術室多螢幕與病房", "branch": "db2", "icon": "🏥", "color": "#0f766e" },
            { "name": "智慧高鐵與智慧電網", "role": "號誌與變電所監控", "branch": "db2", "icon": "🚄", "color": "#0f766e" }
        ]
    },
    "6414": {
        "title": "樺漢 (6414) 工控系統與邊緣 AI 產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "鴻海精密製造體系", "icon": "🦊" },
            { "id": "ub2", "name": "嵌入式工控處理器", "icon": "🧠" },
            { "id": "ub3", "name": "工控通訊模組", "icon": "📡" }
        ],
        "upstreamLeaves": [
            { "name": "鴻海集團 (2317)", "role": "全球組裝與機構資源", "branch": "ub1", "icon": "🦊", "color": "#2563eb" },
            { "name": "英特爾 (Intel)", "role": "邊緣 AI 工業晶片組", "branch": "ub2", "icon": "💻", "color": "#0369a1" },
            { "name": "聯發科 (2454)", "role": "5G 物聯網晶片", "branch": "ub3", "icon": "📶", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "智慧零售與金融自動化", "icon": "💳" },
            { "id": "db2", "name": "歐洲軌道交通與廠務ESG", "icon": "🚆" }
        ],
        "downstreamLeaves": [
            { "name": "跨國連鎖零售超商", "role": "自助結帳 POS 系統", "branch": "db1", "icon": "🏪", "color": "#0f766e" },
            { "name": "國際商業銀行", "role": "新一代多功能 ATM", "branch": "db1", "icon": "💳", "color": "#0f766e" },
            { "name": "歐洲德國國鐵系統", "role": "Kontron 車載通訊", "branch": "db2", "icon": "🚆", "color": "#0f766e" },
            { "name": "半導體高科技廠務", "role": "智慧能源節能監控", "branch": "db2", "icon": "🌱", "color": "#0f766e" }
        ]
    },
    "3706": {
        "title": "神達 (3706) 伺服器與車載電子產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "Intel DSG 伺服器架構", "icon": "💻" },
            { "id": "ub2", "name": "車用 CMOS 鏡頭感測", "icon": "📷" },
            { "id": "ub3", "name": "伺服器主機板零組件", "icon": "🧬" }
        ],
        "upstreamLeaves": [
            { "name": "英特爾 (Intel)", "role": "伺服器 DSG 業務授權", "branch": "ub1", "icon": "💻", "color": "#0369a1" },
            { "name": "索尼 (SONY)", "role": "車規夜視影像感測器", "branch": "ub2", "icon": "📷", "color": "#0284c7" },
            { "name": "金像電 (2368)", "role": "伺服器高多層板", "branch": "ub3", "icon": "🎛️", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "企業資料中心與私有雲", "icon": "☁️" },
            { "id": "db2", "name": "智慧車載與物流聯網", "icon": "🚛" }
        ],
        "downstreamLeaves": [
            { "name": "歐美跨國企業私有雲", "role": "神雲企業級伺服器", "branch": "db1", "icon": "🏢", "color": "#0f766e" },
            { "name": "雲端電信營運商", "role": "邊緣資料中心節點", "branch": "db1", "icon": "☁️", "color": "#0f766e" },
            { "name": "智慧貨運物流車隊", "role": "車載智慧聯網系統", "branch": "db2", "icon": "🚛", "color": "#0f766e" },
            { "name": "Mio 行車安全用戶", "role": "全球消費行車記錄器", "branch": "db2", "icon": "🚗", "color": "#0f766e" }
        ]
    },
    "2352": {
        "title": "佳世達 (2352) 液晶顯示與智慧醫療產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "高階液晶顯示面板", "icon": "🖥️" },
            { "id": "ub2", "name": "顯示驅動控制晶片", "icon": "⚡" },
            { "id": "ub3", "name": "醫療級生物相容材料", "icon": "🏥" }
        ],
        "upstreamLeaves": [
            { "name": "友達光電 (2409)", "role": "醫療與商用面板", "branch": "ub1", "icon": "🖥️", "color": "#0284c7" },
            { "name": "聯詠科技 (3034)", "role": "超高解析驅動 IC", "branch": "ub2", "icon": "⚡", "color": "#0369a1" },
            { "name": "醫療高分子塑膠原料", "role": "血液透析耐用材料", "branch": "ub3", "icon": "🏥", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "商用顯示與視聽會議", "icon": "🏢" },
            { "id": "db2", "name": "明基醫療院所與通路", "icon": "🏥" }
        ],
        "downstreamLeaves": [
            { "name": "跨國企業會議顯示", "role": "BenQ 投影機與商用屏", "branch": "db1", "icon": "🏢", "color": "#0f766e" },
            { "name": "全球醫療院所手術室", "role": "手術用超高清顯示器", "branch": "db2", "icon": "🏥", "color": "#0f766e" },
            { "name": "明基南京/蘇州醫院", "role": "自有三甲綜合醫療院", "branch": "db2", "icon": "🏨", "color": "#0f766e" },
            { "name": "東南亞血液透析中心", "role": "洗腎人工腎臟供貨", "branch": "db2", "icon": "💉", "color": "#0f766e" }
        ]
    },
    "4915": {
        "title": "致伸 (4915) 電腦週邊、車載與聲學感測產業鏈",
        "upstreamBranches": [
            { "id": "ub1", "name": "光學鏡頭與影像晶片", "icon": "📷" },
            { "id": "ub2", "name": "精密微型馬達機構", "icon": "⚙️" },
            { "id": "ub3", "name": "高傳真聲學發聲單體", "icon": "🎵" }
        ],
        "upstreamLeaves": [
            { "name": "大立光 (3008)", "role": "微型高階光學鏡片", "branch": "ub1", "icon": "📷", "color": "#0369a1" },
            { "name": "索尼 (SONY)", "role": "高解析 CMOS 感測器", "branch": "ub1", "icon": "🔬", "color": "#0369a1" },
            { "name": "精密金屬軸心沖壓", "role": "滑鼠滾輪與微動開關", "branch": "ub2", "icon": "⚙️", "color": "#0284c7" },
            { "name": "高階音圈與釹鐵硼磁", "role": "耳機音響驅動單元", "branch": "ub3", "icon": "🎵", "color": "#0284c7" }
        ],
        "downstreamBranches": [
            { "id": "db1", "name": "全球電腦週邊領導品牌", "icon": "🖱️" },
            { "id": "db2", "name": "智慧車載與安防視訊", "icon": "🚗" }
        ],
        "downstreamLeaves": [
            { "name": "羅技 (Logitech)", "role": "高階鍵盤滑鼠代工", "branch": "db1", "icon": "🖱️", "color": "#0f766e" },
            { "name": "全球 PC 筆電大廠", "role": "超薄筆電觸控板組件", "branch": "db1", "icon": "💻", "color": "#0f766e" },
            { "name": "北美頂級電動車廠", "role": "ADAS 前視相機模組", "branch": "db2", "icon": "🚗", "color": "#0f766e" },
            { "name": "國際頂級音響品牌", "role": "高傳真降噪耳機音箱", "branch": "db2", "icon": "🎧", "color": "#0f766e" }
        ]
    }
}

def enrich():
    target_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'sector_stocks.json')
    with open(target_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for item in data:
        sid = item["id"]
        if sid in TREE_CHAINS:
            item["treeChain"] = TREE_CHAINS[sid]
            print(f"Enriched treeChain for {sid} {item['name']}")

    with open(target_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Successfully enriched all stocks with streamlined treeChain!")

if __name__ == '__main__':
    enrich()
