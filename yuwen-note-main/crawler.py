# -*- coding: utf-8 -*-
import requests
import sys
import os
import time
import re
from bs4 import BeautifulSoup

# 从环境变量读取 API Key
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

def crawl_hanchacha(lesson_name):
    """从 hanchacha.com 爬取所有相关资料"""
    print(f"  🔍 正在从 hanchacha.com 搜索《{lesson_name}》...")
    
    all_text = ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        search_url = f"https://hanchacha.com/?s={lesson_name}"
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = soup.find_all('a', href=True)
        found_urls = []
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text().lower()
            if lesson_name.lower() in text and 'hanchacha.com' in href:
                if href not in found_urls:
                    found_urls.append(href)
        
        print(f"    找到 {len(found_urls)} 个相关页面")
        
        for url in found_urls[:3]:
            try:
                page_resp = requests.get(url, headers=headers, timeout=10)
                page_soup = BeautifulSoup(page_resp.text, 'html.parser')
                content_div = page_soup.find('article') or page_soup.find('div', class_='entry-content')
                
                if content_div:
                    text = content_div.get_text(strip=True)
                    text = re.sub(r'\s+', ' ', text)
                    all_text += f"\n\n---\n{text[:1500]}"
            except:
                continue
                
    except Exception as e:
        print(f"  hanchacha 爬取失败: {e}")
    
    return all_text[:4000]

def generate_with_ai(lesson_name, raw_materials):
    """使用 AI 生成详细的学霸笔记"""
    
    print(f"  🤖 AI 状态: {'已启用' if DEEPSEEK_API_KEY else '未配置'}")
    
    if not DEEPSEEK_API_KEY:
        return generate_fallback_note(lesson_name, raw_materials)
    
    try:
        print("  🤖 正在调用 DeepSeek API...")
        
        prompt = f"""你是小学语文特级教师。请为课文《{lesson_name}》生成一份超级详细的学霸笔记。

【要求】
1. 必须像下面示例一样详细、专业
2. 每个表格都要填满具体内容
3. 写出具体的词语、句子、分析、写作技巧
4. 绝对不能留空或用"请根据课文填写"

【参考详细程度】：
《海底世界》示例：
- 课文简介：科普性说明文，从环境、动物、植物、矿产四方面介绍
- 文章结构：表格（部分、自然段、内容、作用）
- 写作特色：对比+拟人，有具体例子和写作小技巧
- 词语积累：必会字词、近义词、反义词、AABC式词语
- 仿写句式：有的...有的...有的...，有原句和仿写
- 课后挑战：3个具体任务

请按以下格式输出：

# 🌊 探秘{lesson_name} · 学霸综合笔记 🐠

> 一份集**知识点、课堂笔记、教学思路**于一体的超实用手册

---

## 📚 一、课文一瞥：它讲了什么？

（写具体内容）

*   **核心问题**：
*   **主要内容**：
*   **中心句**：

---

## 🧱 二、文章结构：总分总，超清晰！

| 部分 | 自然段 | 内容 | 作用 |
|------|--------|------|------|
| 开头 | | | |
| 中间 | | | |
| 结尾 | | | |

> 💡 **写作要点：**

---

## ✨ 三、阅读与写作：深挖课文"宝藏"

### 写作特色分析

| 阅读要点 | 写法分析 | 写作小技巧 |
|----------|----------|------------|
| | | |
| | | |
| | | |

> 💡 **写作要点：**

---

## 📝 四、语言积累：词语库+句式库

### 重点词语

| 类别 | 词语 |
|------|------|
| 必会字词 | |
| 近义词 | |
| 反义词 | |
| 成语/AABC | |

### 仿写句式

> **句式名称**
>
> *   **课文原句**：
> *   **仿写示例**：

---

## 🎯 五、课后挑战：小试牛刀

1. **朗读小能手**：
2. **小小解说员**：
3. **妙笔生花**：

---

【参考资料】
{raw_materials[:3000]}

请直接输出笔记，不要输出解释。"""

        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是小学语文特级教师，擅长写超详细、超专业的课文笔记。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.8,
                "max_tokens": 4500
            },
            timeout=90
        )
        
        if response.status_code == 200:
            result = response.json()
            note = result["choices"][0]["message"]["content"]
            print(f"  ✅ AI 生成成功！笔记长度: {len(note)} 字")
            return note
        else:
            print(f"  ⚠️ AI 调用失败: {response.status_code}")
            return generate_fallback_note(lesson_name, raw_materials)
            
    except Exception as e:
        print(f"  ⚠️ AI 异常: {e}")
        return generate_fallback_note(lesson_name, raw_materials)

def generate_fallback_note(lesson_name, raw_materials):
    """备用笔记"""
    return f"""# 📖 {lesson_name} · 学习笔记

> 正在努力生成中...

---

## 📚 课文内容

{raw_materials[:500] if raw_materials else f"《{lesson_name}》是一篇优美的课文。"}

---

## 📝 学习建议

1. 朗读课文3遍
2. 标出生字词
3. 思考课文主要内容

---

*生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}*
"""

def main():
    if len(sys.argv) < 2:
        print("请提供课文名称")
        sys.exit(1)
    
    lesson_name = sys.argv[1]
    print("=" * 50)
    print(f"🕷️ 正在为《{lesson_name}》生成笔记...")
    print(f"🤖 DeepSeek API: {'已配置' if DEEPSEEK_API_KEY else '未配置'}")
    print("=" * 50)
    
    print("\n⭐ 爬取 hanchacha.com...")
    hanchacha_text = crawl_hanchacha(lesson_name)
    
    print("\n🤖 调用 AI 生成笔记...")
    note = generate_with_ai(lesson_name, hanchacha_text)
    
    os.makedirs('data', exist_ok=True)
    output_file = f"data/{lesson_name}.md"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(note)
    
    print(f"\n✅ 笔记已保存: {output_file}")

if __name__ == "__main__":
    main()
