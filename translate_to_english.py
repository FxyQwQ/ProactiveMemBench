#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Translate ProactiveMemBench datasets from Chinese to English using LLM.

Translates all 5 domains (music, cooking, fitness, pet, travel) and all 6 steps.
Uses batch processing with checkpointing to handle interruptions gracefully.
"""

import sys
import os
os.environ['PYTHONUNBUFFERED'] = '1'
sys.stdout.reconfigure(line_buffering=True)

import json
import time
import requests
import copy
from pathlib import Path

# ========== API Configuration ==========
URL_397B = "http://drhttpsvr.polaris:8000/v1/llm-luban-gzh-Qwen3.5-397B-A17B-0324-14/chat/completions"
MODEL_397B = "llm-luban-gzh-Qwen3.5-397B-A17B-0324-14"
TOKEN = "luban_platform,3de7b3929c2494cf93702c52acd391f32e5ee0375e91efb439f740e96baa4f90"
MAX_TOKENS = 40960

# ========== Path Configuration ==========
BASE_DIR = Path("/mnt/wfs/mmguangmingwfssz/user_fanxfan/ProactiveMemBench")
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "data_en"

DOMAINS = ["music", "cooking", "fitness", "pet", "travel"]
STEPS = [
    "step0_persona.json",
    "step1_concept_pairs.json",
    "step2_associations.json",
    "step3_session_groups.json",
    "step4_conversations.json",
    "step5_proactive_questions.json",
]


def call_llm(system_prompt, user_prompt, max_tokens=MAX_TOKENS, temperature=0.3):
    """Call 397B model (nothink mode)"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    headers = {
        "Content-Type": "application/json",
        "Luban-Request-Trace-ID": "luban_platform_trace_id",
        "Luban-Request-UIN": "luban_platform_uin",
        "Luban-Request-Token": TOKEN,
        "Luban-Request-Business": "15",
    }
    payload = {
        "model": MODEL_397B,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(URL_397B, headers=headers, json=payload, timeout=600)
            if resp.status_code != 200:
                print(f"  [ERROR] HTTP {resp.status_code}: {resp.text[:300]}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return None
            result = resp.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0].get("message", {}).get("content", "").strip()
                return content
            print(f"  [ERROR] Unexpected response: {json.dumps(result, ensure_ascii=False)[:200]}")
            return None
        except Exception as e:
            print(f"  [ERROR] Attempt {attempt+1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                return None
    return None


def extract_json(text):
    """Extract JSON from LLM output"""
    if not text:
        return None
    # Try direct parse
    try:
        return json.loads(text)
    except:
        pass
    # Try to find JSON block in markdown
    import re
    patterns = [
        r'```json\s*\n(.*?)\n\s*```',
        r'```\s*\n(.*?)\n\s*```',
        r'(\[.*\])',
        r'(\{.*\})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                continue
    return None


TRANSLATE_SYSTEM_PROMPT = """You are an expert translator specializing in converting Chinese JSON data to English. 

Rules:
1. Translate ALL Chinese text values to natural, fluent English.
2. Keep JSON structure, keys, and formatting EXACTLY the same.
3. Keep proper nouns that are already in English (e.g., "BBC Radio 3", "Philip Glass", "Bach", "Debussy") unchanged.
4. For Chinese names, transliterate them to Pinyin (e.g., "林晓芸" → "Lin Xiaoyun", "张教授" → "Professor Zhang").
5. For Chinese city names, use standard English names (e.g., "杭州" → "Hangzhou", "成都" → "Chengdu").
6. Keep IDs, timestamps, numbers, and technical fields unchanged.
7. The translation should feel natural as if originally written in English, not a literal translation.
8. Output ONLY the translated JSON, no explanations or markdown wrapping."""


def translate_chunk(data_chunk, context_hint=""):
    """Translate a chunk of data using LLM"""
    user_prompt = f"""Translate the following JSON data from Chinese to English. Keep all JSON keys unchanged, only translate the Chinese text values.

{context_hint}

JSON to translate:
```json
{json.dumps(data_chunk, ensure_ascii=False, indent=2)}
```

Output the translated JSON directly:"""

    result = call_llm(TRANSLATE_SYSTEM_PROMPT, user_prompt)
    if not result:
        return None
    
    translated = extract_json(result)
    return translated


def translate_persona(data, domain):
    """Translate persona (single object, translate in one go)"""
    print(f"  Translating persona...")
    context = f"This is a user persona for the '{domain}' domain. Translate all Chinese text to English."
    translated = translate_chunk(data, context)
    if translated:
        return translated
    print("  [WARN] Persona translation failed, retrying...")
    time.sleep(5)
    return translate_chunk(data, context)


def translate_list_in_batches(data, domain, step_name, batch_size=5):
    """Translate a list of items in batches"""
    if not isinstance(data, list):
        return translate_chunk(data, f"Domain: {domain}, Step: {step_name}")
    
    total = len(data)
    translated_items = []
    
    for i in range(0, total, batch_size):
        batch = data[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches} (items {i+1}-{min(i+batch_size, total)}/{total})...")
        
        context = f"Domain: {domain}. This is from '{step_name}'. Translate Chinese text values to English."
        result = translate_chunk(batch, context)
        
        if result and isinstance(result, list) and len(result) == len(batch):
            translated_items.extend(result)
        else:
            # Retry once
            print(f"  [WARN] Batch {batch_num} failed or length mismatch, retrying...")
            time.sleep(5)
            result = translate_chunk(batch, context)
            if result and isinstance(result, list) and len(result) == len(batch):
                translated_items.extend(result)
            else:
                # Fall back to one-by-one translation
                print(f"  [WARN] Batch retry failed, translating one by one...")
                for j, item in enumerate(batch):
                    single_result = translate_chunk([item], context)
                    if single_result and isinstance(single_result, list):
                        translated_items.extend(single_result)
                    else:
                        print(f"  [ERROR] Item {i+j+1} translation failed, keeping original")
                        translated_items.append(item)
        
        # Rate limiting
        time.sleep(1)
    
    return translated_items


def translate_conversations(data, domain):
    """Translate conversations - handle each session separately due to size"""
    translated_sessions = []
    total = len(data)
    
    for idx, session in enumerate(data):
        print(f"  Session {idx+1}/{total}...")
        context = f"Domain: {domain}. This is a conversation session. Translate the 'content' field and any other Chinese text to English. Keep timestamps, IDs, roles unchanged."
        
        result = translate_chunk(session, context)
        if result:
            translated_sessions.append(result)
        else:
            # Retry
            print(f"  [WARN] Session {idx+1} failed, retrying...")
            time.sleep(5)
            result = translate_chunk(session, context)
            if result:
                translated_sessions.append(result)
            else:
                print(f"  [ERROR] Session {idx+1} translation failed, keeping original")
                translated_sessions.append(session)
        
        time.sleep(1)
    
    return translated_sessions


def process_domain(domain):
    """Process all steps for a single domain"""
    domain_dir = DATA_DIR / domain
    output_domain_dir = OUTPUT_DIR / domain
    output_domain_dir.mkdir(parents=True, exist_ok=True)
    
    for step_file in STEPS:
        input_path = domain_dir / step_file
        output_path = output_domain_dir / step_file
        
        # Skip if already translated
        if output_path.exists():
            print(f"  [{domain}/{step_file}] Already exists, skipping.")
            continue
        
        if not input_path.exists():
            print(f"  [{domain}/{step_file}] Source not found, skipping.")
            continue
        
        print(f"\n  === Translating {domain}/{step_file} ===")
        
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Choose translation strategy based on step
        if step_file == "step0_persona.json":
            translated = translate_persona(data, domain)
        elif step_file == "step4_conversations.json":
            translated = translate_conversations(data, domain)
        elif step_file == "step5_proactive_questions.json":
            translated = translate_list_in_batches(data, domain, step_file, batch_size=5)
        elif step_file == "step1_concept_pairs.json":
            translated = translate_list_in_batches(data, domain, step_file, batch_size=5)
        elif step_file == "step2_associations.json":
            translated = translate_list_in_batches(data, domain, step_file, batch_size=10)
        elif step_file == "step3_session_groups.json":
            # Session groups are usually smaller
            if isinstance(data, list):
                translated = translate_list_in_batches(data, domain, step_file, batch_size=5)
            else:
                translated = translate_chunk(data, f"Domain: {domain}. Session grouping data.")
        else:
            translated = translate_chunk(data, f"Domain: {domain}")
        
        if translated:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(translated, f, ensure_ascii=False, indent=2)
            print(f"  ✓ Saved {output_path}")
        else:
            print(f"  ✗ FAILED to translate {domain}/{step_file}")


def main():
    print("=" * 60)
    print("ProactiveMemBench - Translate to English")
    print("=" * 60)
    print(f"Source: {DATA_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Domains: {DOMAINS}")
    print()
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    for domain in DOMAINS:
        print(f"\n{'='*60}")
        print(f"  Domain: {domain}")
        print(f"{'='*60}")
        process_domain(domain)
    
    # After all translations complete, replace data/ with data_en/
    print(f"\n{'='*60}")
    print("Translation complete!")
    print(f"English data saved to: {OUTPUT_DIR}")
    print()
    print("To replace the original data with English version:")
    print(f"  rm -rf {DATA_DIR}")
    print(f"  mv {OUTPUT_DIR} {DATA_DIR}")
    print("="*60)


if __name__ == "__main__":
    main()
