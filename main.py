#!/usr/bin/env python3
"""
Notion 自动关联脚本
自动关联"运动"数据库和"日记中心"数据库中日期相同的项

用法:
    python3 main.py

环境变量:
    NOTION_TOKEN: Notion API Token (必需)
    
可以在 .env 文件中配置，或在 GitHub Secrets 中设置 NOTION_TOKEN
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ============== 配置 ==============
# 数据库 Data Source ID (不是 Database ID!)
SPORTS_DATA_SOURCE = "26333b33-7f23-81ed-b436-000b62507748"  # 运动
DIARY_DATA_SOURCE = "6d280b25-c22e-432a-a8e9-22e72617205e"  # 日记中心

# 属性名
SPORTS_DATE_PROP = "开始时间"
SPORTS_RELATION_PROP = "📅 日记中心"
DIARY_DATE_PROP = "日期"
DIARY_RELATION_PROP = "运动"

# 查询范围（天）
QUERY_DAYS = 7

# ============== API 调用 ==============

def get_token() -> str:
    """获取 Notion API Token"""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        # 尝试从文件读取（本地开发用）
        try:
            script_path = os.path.expanduser(
                "~/Library/Application Support/QClaw/openclaw/config/skills/notion/get-token.sh"
            )
            if os.path.exists(script_path):
                result = subprocess.run(
                    ["bash", script_path],
                    capture_output=True,
                    text=True
                )
                token = result.stdout.strip()
        except Exception:
            pass
    
    if not token or token == "ERROR":
        raise RuntimeError("未找到 NOTION_TOKEN 环境变量，请设置后再试")
    
    return token


def query_data_source(token: str, data_source_id: str, date_prop: str, days: int = 7) -> List[Dict]:
    """查询数据源，获取近 N 天的记录"""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    url = f"https://api.notion.com/v1/data_sources/{data_source_id}/query"
    
    payload = {
        "filter": {
            "property": date_prop,
            "date": {
                "on_or_after": start_date
            }
        },
        "page_size": 100
    }
    
    all_results = []
    next_cursor = None
    
    while True:
        if next_cursor:
            payload["start_cursor"] = next_cursor
        
        cmd = [
            "curl", "-s", "-X", "POST", url,
            "-H", f"Authorization: Bearer {token}",
            "-H", "Notion-Version: 2025-09-03",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"API 请求失败: {result.stderr}")
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"API 返回非 JSON 格式: {result.stdout[:500]}")
        
        all_results.extend(data.get("results", []))
        
        if not data.get("has_more"):
            break
        
        next_cursor = data.get("next_cursor")
        
        # 防止无限循环
        if len(all_results) > 1000:
            print("⚠️ 数据量过大，截断到 1000 条")
            break
    
    return all_results


def extract_date(page: Dict, date_prop: str) -> Optional[str]:
    """从页面中提取日期（只取日期部分 YYYY-MM-DD）"""
    properties = page.get("properties", {})
    date_prop_data = properties.get(date_prop, {})
    
    if date_prop_data.get("type") == "date":
        date_data = date_prop_data.get("date")
        if date_data and date_data.get("start"):
            # 提取日期部分 (YYYY-MM-DD)
            return date_data["start"][:10]
    
    return None


def extract_existing_relations(page: Dict, relation_prop: str) -> List[str]:
    """提取已有的关联页面 ID"""
    properties = page.get("properties", {})
    relation_data = properties.get(relation_prop, {})
    
    if relation_data.get("type") == "relation":
        return [r.get("id") for r in relation_data.get("relation", []) if r.get("id")]
    
    return []


def update_page_relation(token: str, page_id: str, relation_prop: str, relation_ids: List[str]) -> bool:
    """更新页面的关联属性"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    
    properties = {
        relation_prop: {
            "relation": [{"id": rid} for rid in relation_ids]
        }
    }
    
    cmd = [
        "curl", "-s", "-X", "PATCH", url,
        "-H", f"Authorization: Bearer {token}",
        "-H", "Notion-Version: 2025-09-03",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"properties": properties})
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  ⚠️ 更新页面失败: {result.stderr[:100]}")
        return False
    
    try:
        response = json.loads(result.stdout)
        if response.get("object") == "error":
            print(f"  ⚠️ API 错误: {response.get('message', 'Unknown error')}")
            return False
    except json.JSONDecodeError:
        print(f"  ⚠️ 响应解析失败")
        return False
    
    return True


# ============== 主逻辑 ==============

def main():
    """主函数"""
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始自动关联...")
    print(f"📅 查询范围: 近 {QUERY_DAYS} 天")
    print()
    
    try:
        # 获取 Token
        token = get_token()
        print("✅ Token 获取成功")
        
        # 查询近期的运动记录
        print(f"\n🏃 查询运动数据库 (近 {QUERY_DAYS} 天)...")
        sports_pages = query_data_source(token, SPORTS_DATA_SOURCE, SPORTS_DATE_PROP, QUERY_DAYS)
        print(f"   找到 {len(sports_pages)} 条运动记录")
        
        # 查询近期的日记中心记录
        print(f"\n📖 查询日记中心数据库 (近 {QUERY_DAYS} 天)...")
        diary_pages = query_data_source(token, DIARY_DATA_SOURCE, DIARY_DATE_PROP, QUERY_DAYS)
        print(f"   找到 {len(diary_pages)} 条日记记录")
        
        # 构建日期 -> 日记页面 映射
        diary_date_map: Dict[str, Dict] = {}
        for page in diary_pages:
            date = extract_date(page, DIARY_DATE_PROP)
            if date:
                diary_date_map[date] = page
        
        print(f"\n🔗 开始匹配并关联...")
        print("-" * 50)
        
        linked_count = 0
        skipped_count = 0
        
        for sports_page in sports_pages:
            sports_id = sports_page["id"]
            sports_date = extract_date(sports_page, SPORTS_DATE_PROP)
            sports_title = ""
            try:
                title_prop = sports_page.get("properties", {}).get("标题", {})
                if title_prop.get("title"):
                    sports_title = title_prop["title"][0].get("plain_text", "")
            except:
                pass
            
            if not sports_date:
                skipped_count += 1
                continue
            
            # 检查已有的关联
            existing_relations = extract_existing_relations(sports_page, SPORTS_RELATION_PROP)
            
            # 查找匹配的日记
            if sports_date in diary_date_map:
                diary_page = diary_date_map[sports_date]
                diary_id = diary_page["id"]
                
                # 如果运动记录还没有关联这个日记
                if diary_id not in existing_relations:
                    # 添加关联（保留现有关联 + 新增）
                    new_relations = existing_relations + [diary_id]
                    
                    success = update_page_relation(token, sports_id, SPORTS_RELATION_PROP, new_relations)
                    
                    if success:
                        print(f"   ✅ 关联成功: [{sports_date}] {sports_title}")
                        linked_count += 1
                    else:
                        print(f"   ❌ 关联失败: [{sports_date}] {sports_title}")
                else:
                    print(f"   ⏭️ 已有关联: [{sports_date}] {sports_title}")
            else:
                print(f"   ⏭️ 无匹配日记: [{sports_date}] {sports_title}")
        
        print("-" * 50)
        print(f"\n🎉 完成！")
        print(f"   - 新增关联: {linked_count} 条")
        print(f"   - 已有关联: {len(sports_pages) - skipped_count - linked_count} 条")
        print(f"   - 跳过/无日期: {skipped_count} 条")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
