import json
import os

SUBGROUP_MAP = {
    # 1. AI 伺服器整機與系統代工 (ODM)
    "2382": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": True,
        "leaderWhy": "單季合併營收衝破 1.1 兆元，NVIDIA GB200 NVL72 首發戰略代工廠，微軟、Google、AWS、Meta 四大 CSP 白牌直供市占全球第一。"
    },
    "6669": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": ""
    },
    "3231": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": ""
    },
    "2356": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": ""
    },
    "2376": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": ""
    },
    "3706": {
        "subGroup": "odm",
        "subGroupName": "AI伺服器整機與系統代工",
        "groupBadge": "算力系統核心",
        "isLeader": False,
        "leaderWhy": ""
    },

    # 2. 伺服器關鍵零組件與散熱
    "2059": {
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": True,
        "leaderWhy": "手握全球逾 3,000 項專利，毛利率高達 68.2% 冠絕台股硬體族群，全球唯一量產通過 GB200 1.3 噸抗震認證之重型導軌獨占龍頭。"
    },
    "3017": {
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": True,
        "leaderWhy": "水冷板、分流管 (Manifold)、CDU 冷卻分配單元一條龍全自製，通過 NVIDIA 官方嚴苛驗證，伺服器散熱營收規模與水冷出貨居台廠第一。"
    },
    "3324": {
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": False,
        "leaderWhy": ""
    },
    "8210": {
        "subGroup": "components",
        "subGroupName": "關鍵零組件與水冷散熱",
        "groupBadge": "高專利高毛利",
        "isLeader": False,
        "leaderWhy": ""
    },

    # 3. 工業電腦與邊緣物聯網
    "2395": {
        "subGroup": "ipc_iot",
        "subGroupName": "工業電腦與邊緣物聯網",
        "groupBadge": "工業AI與自動化",
        "isLeader": True,
        "leaderWhy": "全球工業電腦 (IPC) 市占率逾 35% 稱霸全球超過二十年，毛利率長年穩健維持 40% 以上，為全球智慧工廠與邊緣 AI 推論標準制定者。"
    },
    "6414": {
        "subGroup": "ipc_iot",
        "subGroupName": "工業電腦與邊緣物聯網",
        "groupBadge": "工業AI與自動化",
        "isLeader": False,
        "leaderWhy": ""
    },

    # 4. 電腦品牌與電競旗艦
    "2357": {
        "subGroup": "brand_pc",
        "subGroupName": "電腦品牌與電競旗艦",
        "groupBadge": "全球終端品牌",
        "isLeader": True,
        "leaderWhy": "全球主機板與電競 ROG 第一品牌，近四季 EPS 高達 42.5 元，手握國家級 AI 超級電腦大型伺服器標案，跨界展現強大系統實力。"
    },
    "2377": {
        "subGroup": "brand_pc",
        "subGroupName": "電腦品牌與電競旗艦",
        "groupBadge": "全球終端品牌",
        "isLeader": False,
        "leaderWhy": ""
    },

    # 5. 週邊設備與智慧顯示
    "2352": {
        "subGroup": "peripherals",
        "subGroupName": "週邊設備與智慧顯示",
        "groupBadge": "視覺聲學與光學",
        "isLeader": False,
        "leaderWhy": ""
    },
    "4915": {
        "subGroup": "peripherals",
        "subGroupName": "週邊設備與智慧顯示",
        "groupBadge": "視覺聲學與光學",
        "isLeader": True,
        "leaderWhy": "電腦高階週邊、車載 ADAS 鏡頭模組與頂級電競聲學領導大廠，高附加價值產品比重攀升，兼具穩定高殖利率。"
    }
}

def update_sector_json():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(base_dir, 'data', 'sector_stocks.json')
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        sid = item.get('id')
        if sid in SUBGROUP_MAP:
            info = SUBGROUP_MAP[sid]
            item['subGroup'] = info['subGroup']
            item['category'] = info['subGroup'] # keep consistent with filter tabs
            item['subGroupName'] = info['subGroupName']
            item['groupBadge'] = info['groupBadge']
            item['isLeader'] = info['isLeader']
            item['leaderWhy'] = info['leaderWhy']
            print(f"Updated {sid} {item.get('name')}: {info['subGroupName']} (Leader: {info['isLeader']})")
            
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print("Successfully updated sector_stocks.json with subGroup and leader information!")

if __name__ == '__main__':
    update_sector_json()
