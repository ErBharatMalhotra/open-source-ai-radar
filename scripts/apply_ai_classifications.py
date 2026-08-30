"""Apply AI-classified categories to uncategorized repos.
Run AFTER schedule finishes (not during).

Usage: uv run python scripts/apply_ai_classifications.py
"""
import sqlite3
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# My classifications based on description + topics analysis
CLASSIFICATIONS = {
    # AI Agents
    "huginn/huginn": ("AI Agents", "task agent"),
    "zai-org/Open-AutoGLM": ("AI Agents", "coding agent"),
    "tanweai/pua": ("AI Agents", "task agent"),
    "1weiho/open-slide": ("AI Agents", "coding agent"),
    "vercel/eve": ("AI Agents", "task agent"),
    "millionco/expect": ("AI Agents", "coding agent"),
    "aipoch/open-science": ("AI Agents", "research agent"),
    "YeQing17-2026/OmniAgent": ("AI Agents", "task agent"),
    "kaqijiang/Auto-GPT-ZH": ("AI Agents", "task agent"),
    "jd-opensource/OxyGent": ("AI Agents", "task agent"),
    "ShawnPana/phone-harness": ("AI Agents", "task agent"),
    "nullclaw/nullhub": ("AI Agents", "task agent"),
    "chaxiu/munk-ai": ("AI Agents", "task agent"),
    "RecursiveMAS/RecursiveMAS": ("AI Agents", "task agent"),
    "SimWorld-AI/SimWorld": ("AI Agents", "task agent"),
    "isaiahbjork/Auto-GPT-MetaTrader-Plugin": ("AI Agents", "task agent"),
    "ownpilot/OwnPilot": ("AI Agents", "task agent"),
    "genlayerlabs/genworlds": ("AI Agents", "task agent"),
    "isaiahbjork/Auto-GPT-Crypto-Plugin": ("AI Agents", "task agent"),
    "AI45Lab/TrinityGuard": ("AI Agents", "task agent"),
    "NVIDIA-Omniverse/usd-content-agents": ("AI Agents", "task agent"),
    "yuzhenmao/DeLM": ("AI Agents", "task agent"),
    "kokolerk/TCOD": ("AI Agents", "task agent"),
    "MasoudJTehrani/PCLA": ("AI Agents", "task agent"),
    "mb-mal/awesome-ai-agents-frameworks": ("AI Agents", "task agent"),
    "buiphucminhtam/forgewright": ("AI Agents", "task agent"),

    # AI Coding Tools
    "antiwork/shortest": ("AI Coding Tools", "code completion"),
    "ycm-core/ycmd": ("AI Coding Tools", "code completion"),
    "notnotype/neuro-book": ("AI Coding Tools", "ide extension"),
    "jupyterlite/ai": ("AI Coding Tools", "code completion"),
    "iuiaeng2005/deepseek-vision-skill": ("AI Coding Tools", "cli tool"),

    # RAG
    "langflow-ai/openrag": ("RAG", "rag framework"),
    "IdolLab/RAGTrack": ("RAG", "rag framework"),
    "syr-cn/AutoRefine": ("RAG", "rag framework"),
    "aws-samples/semantic-search-with-amazon-opensearch": ("RAG", "vector database"),

    # LLM Frameworks
    "googleapis/python-genai": ("LLM Frameworks", "inference engine"),
    "googleapis/go-genai": ("LLM Frameworks", "inference engine"),
    "googleapis/java-genai": ("LLM Frameworks", "inference engine"),
    "googleapis/dotnet-genai": ("LLM Frameworks", "inference engine"),
    "chenking2020/FindTheChatGPTer": ("LLM Frameworks", "inference engine"),
    "kyegomez/the-compiler": ("LLM Frameworks", "inference engine"),
    "mohammad-atikuzzaman/aiArticleGenerator": ("LLM Frameworks", "inference engine"),
    "noeigenstate/AI-Article-Writing-without-AI-feel": ("LLM Frameworks", "inference engine"),
    "xiaoou-waou/xiaoou-ai-article-writer": ("LLM Frameworks", "inference engine"),

    # Generative AI
    "Stability-AI/stable-audio-tools": ("Generative AI", "audio"),
    "haidog-yaqub/MeanFlow": ("Generative AI", "image"),
    "visualbruno/3DGenStudio": ("Generative AI", "3d"),
    "soraw-ai/Awesome-Text-to-Video-Generation": ("Generative AI", "video"),
    "m1balcerak/EnergyMatching": ("Generative AI", "image"),
    "LOGOS-Hub/LOGOS": ("Generative AI", "image"),
    "princepainter/Comfyui-PainterFluxImageEdit": ("Generative AI", "image"),
    "forestdb/forestdb.org": ("Generative AI", "image"),
    "Ghy0501/Awesome-Continual-Learning-in-Generative-Models": ("Generative AI", "image"),
    "KohakuBlueleaf/KGen": ("Generative AI", "image"),
    "Rookie143/Awesome-Embodied-AI-Safety": ("AI Safety & Alignment", "guardrails"),
    "Stability-AI/stable-audio-metrics": ("Evaluation & Benchmarks", "benchmark"),
    "evedesignbio/evedesign": ("Generative AI", "image"),
    "wendashi/awesome-3D-Generative-Models": ("Generative AI", "3d"),
    "smithhenryd/cgm": ("Generative AI", "image"),
    "neptune-T/Awesome-Style-Transfer": ("Generative AI", "image"),
    "giacomo-janson/sam2": ("Generative AI", "image"),
    "xmz111/ReChannel": ("Generative AI", "image"),
    "GAP-LAB-CUHK-SZ/LoFA": ("Generative AI", "image"),
    "YueHan99/Ink3D.TextureGen": ("Generative AI", "3d"),
    "cpfpengfei/PCFM": ("Generative AI", "image"),
    "yuanzhang7/Awesome-Generative-Models-in-Pathology": ("Generative AI", "image"),
    "gojasper/nano-t2i": ("Generative AI", "image"),
    "syjmelody/RankE": ("Generative AI", "image"),
    "zfrsgtcu/ComfyUI-ZFRNodes": ("Generative AI", "image"),
    "Harvard-AI-and-Robotics-Lab/DeltaRectifiedFlowSampling": ("Generative AI", "image"),
    "nianbai006/SDG": ("Generative AI", "image"),
    "XTOGENY/ai-artist-tool": ("Generative AI", "image"),
    "Justin-sky/ai-art-engine": ("Generative AI", "image"),
    "luo-group/SPURS": ("Generative AI", "image"),
    "bips-hb/arfpy": ("Generative AI", "image"),
    "micky-li-hd/CoCo": ("Generative AI", "image"),
    "zhxie0117/VideoRAE": ("Generative AI", "video"),

    # Multimodal AI
    "zju3dv/MatchAnything": ("Multimodal AI", "vision-language"),
    "hustvl/Senna": ("Multimodal AI", "vision-language"),
    "GingerCohle/VLMCSHFG": ("Multimodal AI", "vision-language"),
    "BAAI-DCAI/SpatialBot": ("Multimodal AI", "vision-language"),
    "hustvl/InfiniteVL": ("Multimodal AI", "vision-language"),
    "WJ-CV/VGGDrive": ("Multimodal AI", "vision-language"),
    "HVision-NKU/GlimpsePrune": ("Multimodal AI", "vision-language"),
    "ZJU-REAL/SpatialLadder": ("Multimodal AI", "vision-language"),
    "tim-learn/Awesome-LabelFree-VLMs": ("Multimodal AI", "vision-language"),
    "FeiElysia/Tempo": ("Multimodal AI", "vision-language"),
    "IRIP-BUAA/A-Survey-on-Remote-Sensing-Foundation-Models-From-Vision-to-Multimodality": ("Multimodal AI", "vision-language"),
    "kdariina/CLIP-not-BoW-unimodally": ("Multimodal AI", "vision-language"),
    "Lzy-dot/SpecFlow": ("Multimodal AI", "vision-language"),

    # Evaluation & Benchmarks
    "llm2014/llm_benchmark": ("Evaluation & Benchmarks", "benchmark"),
    "huggingface/open_asr_leaderboard": ("Evaluation & Benchmarks", "benchmark"),
    "EdinburghNLP/MMLongBench": ("Evaluation & Benchmarks", "benchmark"),
    "asqi-engineer/asqi-engineer": ("Evaluation & Benchmarks", "evaluation framework"),
    "BROccoLi-921/AI-testing-evaluation": ("Evaluation & Benchmarks", "evaluation framework"),
    "kwatcharasupat/latte": ("Evaluation & Benchmarks", "benchmark"),
    "open-experiments/telcoaibench": ("Evaluation & Benchmarks", "benchmark"),
    "gbstox/agronomy_llm_benchmarking": ("Evaluation & Benchmarks", "benchmark"),
    "Intelligent-Drug-Discovery-Lab/MolGenBench": ("Evaluation & Benchmarks", "benchmark"),
    "de-Boer-Lab/Genomic-API-for-Model-Evaluation": ("Evaluation & Benchmarks", "benchmark"),
    "wangxian001/SQL_LLM_benchmark": ("Evaluation & Benchmarks", "benchmark"),
    "lfoppiano/MatSci-LumEn": ("Evaluation & Benchmarks", "benchmark"),
    "HungBil/AI-TEST": ("Evaluation & Benchmarks", "evaluation framework"),

    # AI Safety & Alignment
    "OWASP/www-project-ai-testing-guide": ("AI Safety & Alignment", "guardrails"),
    "liudaizong/Awesome-LVLM-Attack": ("AI Safety & Alignment", "guardrails"),
    "XuankunRong/Awesome-LVLM-Safety": ("AI Safety & Alignment", "guardrails"),
    "jbarach2012/AIBF_API": ("AI Safety & Alignment", "bias detection"),
    "privateai/deid-examples": ("AI Safety & Alignment", "content filtering"),
    "hackclub/ai-safety-dance": ("AI Safety & Alignment", "guardrails"),
    "SomaxSoma/AI-Safety-Research-Tracker": ("AI Safety & Alignment", "guardrails"),
    "coalition-for-health-ai/responsible-ai-content": ("AI Safety & Alignment", "guardrails"),
    "aws-samples/responsible_ai_reduce_hallucinations_for_genai_apps": ("AI Safety & Alignment", "guardrails"),
    "kjam/secure-and-private-ai-products-masterclass": ("AI Safety & Alignment", "guardrails"),
    "watadarkstar/react-native-nsfw-detector": ("AI Safety & Alignment", "content filtering"),
    "Ranjith00005/BiasLens": ("AI Safety & Alignment", "bias detection"),
    "mit-ll-ai-technology/maite": ("AI Safety & Alignment", "guardrails"),

    # Local AI
    "ModalityDance/PalmClaw": ("Local AI", "local runner"),
    "jamjamjon/usls": ("Local AI", "local runner"),
    "software-mansion-labs/private-mind": ("Local AI", "privacy tool"),
    "OpenSecretCloud/Maple": ("Local AI", "privacy tool"),
    "ZeroTricks/lumo-tamer": ("Local AI", "privacy tool"),
    "FutureProofHomes/Satellite1-ESPHome": ("Local AI", "local runner"),
    "icakinser/mlx-flux2-swift": ("Local AI", "local runner"),
    "Dstack-TEE/private-ai-gateway": ("Local AI", "privacy tool"),
    "deokwons9004dev/Canto-Releases": ("Local AI", "privacy tool"),
    "lshl-520/RuoBai": ("Local AI", "privacy tool"),
    "avbiswas/neural-txt": ("Local AI", "local runner"),

    # AI Infrastructure
    "tensorflow/tfx": ("AI Infrastructure", "orchestration"),
    "google/visualblocks": ("AI Infrastructure", "orchestration"),
    "BiomedSciAI/causallib": ("AI Infrastructure", "orchestration"),
    "jpmml/jpmml-sparkml": ("AI Infrastructure", "orchestration"),
    "jpmml/pyspark2pmml": ("AI Infrastructure", "orchestration"),
    "NVlabs/timeloop": ("AI Infrastructure", "model serving"),
    "HewlettPackard/cmf": ("AI Infrastructure", "orchestration"),
    "emre-kocyigit/phishing-website-detection-content-based": ("AI Infrastructure", "orchestration"),
    "mlspec/MLSpec": ("AI Infrastructure", "orchestration"),
    "ion-elgreco/rivers": ("AI Infrastructure", "orchestration"),
    "RamiKrispin/pydata-ny-ga-workshop": ("AI Infrastructure", "orchestration"),
    "ciaren-labs/Ciaren": ("AI Infrastructure", "orchestration"),
    "sean-adamsex7235/aion-gridload-ml-2026": ("AI Infrastructure", "orchestration"),
    "RasmussenLab/MOVE": ("AI Infrastructure", "orchestration"),
}

def main():
    db_path = Path("data/radar.db")
    if not db_path.exists():
        print("Database not found!")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get current uncategorized repos
    repos = conn.execute("""
        SELECT r.full_name, r.description, r.topics, r.language
        FROM repositories r
        LEFT JOIN ai_analysis a ON r.full_name = a.repo_full_name
        WHERE a.repo_full_name IS NULL 
           OR a.category = '' 
           OR a.category = 'Uncategorized'
    """).fetchall()

    print(f"Found {len(repos)} uncategorized repos")
    print(f"Classified {len(CLASSIFICATIONS)} repos")
    print()

    updated = 0
    skipped = 0

    for repo in repos:
        fn = repo["full_name"]
        if fn in CLASSIFICATIONS:
            category, sub_category = CLASSIFICATIONS[fn]
            confidence = 0.9  # High confidence (AI classified)
            matched_by = "ai_manual"
            
            # Insert or update ai_analysis
            conn.execute("""
                INSERT INTO ai_analysis (repo_full_name, category, sub_category, confidence, matched_by, timestamp)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(repo_full_name) DO UPDATE SET
                    category = excluded.category,
                    sub_category = excluded.sub_category,
                    confidence = excluded.confidence,
                    matched_by = excluded.matched_by,
                    timestamp = excluded.timestamp
            """, (fn, category, sub_category, confidence, matched_by))
            updated += 1
            print(f"  OK {fn} -> {category}")
        else:
            skipped += 1

    conn.commit()
    conn.close()

    print()
    print(f"Updated: {updated}")
    print(f"Skipped (already classified or not AI): {skipped}")
    print(f"Database: {db_path}")

if __name__ == "__main__":
    main()
