"""Live RAGAS execution — pure-live semantic RAG evaluation.

For each benchmark question we (1) retrieve real evidence with the production
RetrievalService, (2) generate an answer grounded in that evidence with an LLM, and
(3) score the (question, retrieved_contexts, response, reference) tuple with real
``ragas.evaluate`` metrics. No fabricated/offline scores are used here.

Judge + generator model default to ``gpt-5-mini`` (override via RAGAS_JUDGE_MODEL /
RAGAS_GEN_MODEL). This is an EVAL-time LLM, intentionally separate from the production
report-model gate.

Failure is honest: if ragas / langchain / the model is unavailable, we return
``execution_status`` describing why and empty scores (the caller marks the metric
blocked) — we never invent numbers.
"""
from __future__ import annotations

import os
from typing import Any, Callable

RAGAS_METRIC_IDS = ("context_precision", "context_recall", "faithfulness", "response_relevancy")

_DEFAULT_JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "gpt-5-mini")
_DEFAULT_GEN_MODEL = os.getenv("RAGAS_GEN_MODEL", _DEFAULT_JUDGE_MODEL)
_DEFAULT_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


def _default_generate(question: str, contexts: list[str], model: str) -> str:
    """Generate a grounded answer from retrieved contexts using OpenAI chat."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    context_block = "\n\n".join(contexts) if contexts else "(không có bằng chứng truy hồi được)"
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là trợ lý phân tích tài chính. Chỉ trả lời dựa trên BẰNG CHỨNG được cung "
                "cấp. Nếu bằng chứng không đủ, nói rõ là không đủ dữ liệu. Trả lời ngắn gọn, "
                "kèm con số nếu có."
            ),
        },
        {
            "role": "user",
            "content": f"Câu hỏi: {question}\n\nBẰNG CHỨNG:\n{context_block}\n\nTrả lời:",
        },
    ]
    # gpt-5.x are reasoning models: they use max_completion_tokens (not max_tokens) and
    # spend tokens on hidden reasoning, so allow generous headroom or the answer is empty.
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, max_completion_tokens=2048,
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model, messages=messages, max_tokens=512,
        )
    return (resp.choices[0].message.content or "").strip()


def run_live_ragas(
    samples: list[dict[str, Any]],
    ticker: str,
    retrieve: Callable[..., list[Any]],
    *,
    judge_model: str | None = None,
    gen_model: str | None = None,
    embed_model: str | None = None,
    top_k: int = 5,
    generate: Callable[[str, list[str], str], str] | None = None,
) -> dict[str, Any]:
    """Run real ragas over live-retrieved contexts + generated answers.

    Each sample needs ``question`` and ``reference`` (expected answer). ``contexts`` are
    retrieved live (the sample's pre-baked contexts, if any, are ignored).
    """
    if not samples:
        return _result("not_executed", "ragas_dataset_missing", {}, [])

    judge_model = judge_model or _DEFAULT_JUDGE_MODEL
    gen_model = gen_model or _DEFAULT_GEN_MODEL
    embed_model = embed_model or _DEFAULT_EMBED_MODEL
    generate = generate or _default_generate

    if not os.getenv("OPENAI_API_KEY"):
        return _result("framework_unavailable", "openai_api_key_missing", {}, [])

    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )
    except Exception as exc:  # noqa: BLE001 — missing deps -> honest framework_unavailable
        return _result("framework_unavailable", str(exc), {}, [])

    # Build the live dataset: retrieve real evidence + generate grounded answers.
    enriched: list[dict[str, Any]] = []
    ragas_rows: list[Any] = []
    for sample in samples:
        question = str(sample.get("question") or "")
        reference = str(sample.get("expected_answer") or sample.get("reference") or "")
        fiscal_year = sample.get("fiscal_year")
        try:
            chunks = retrieve(ticker=ticker, query=question, fiscal_year=fiscal_year, top_k=top_k)
        except Exception:  # noqa: BLE001
            chunks = []
        contexts = [getattr(c, "chunk_text", "") or "" for c in list(chunks)[:top_k]]
        try:
            response = generate(question, contexts, gen_model)
        except Exception as exc:  # noqa: BLE001 — a generation failure is recorded, not faked
            response = ""
            sample = {**sample, "_generation_error": str(exc)}
        enriched.append({
            "id": sample.get("id"),
            "question": question,
            "reference": reference,
            "retrieved_contexts": contexts,
            "response": response,
        })
        ragas_rows.append(SingleTurnSample(
            user_input=question,
            retrieved_contexts=contexts or [""],
            response=response or "",
            reference=reference or "",
        ))

    try:
        # gpt-5.x only support the default temperature (1); ragas otherwise sets a lower
        # value per metric and the call 400s. bypass_temperature stops ragas from
        # overriding it (same path ragas uses for the OpenAI o1 series).
        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(model=judge_model, temperature=1), bypass_temperature=True,
        )
        evaluator_embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=embed_model))
        metrics = [
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
            Faithfulness(),
            ResponseRelevancy(),
        ]
        result = evaluate(
            EvaluationDataset(samples=ragas_rows),
            metrics=metrics,
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            show_progress=False,
        )
    except Exception as exc:  # noqa: BLE001 — model/provider errors stay visible
        return _result("execution_error", str(exc), {}, enriched)

    df = result.to_pandas()
    # Map ragas column names -> our metric ids.
    col_map = {
        "llm_context_precision_with_reference": "context_precision",
        "context_precision": "context_precision",
        "context_recall": "context_recall",
        "faithfulness": "faithfulness",
        "answer_relevancy": "response_relevancy",
        "response_relevancy": "response_relevancy",
    }
    scores: dict[str, float] = {}
    per_metric_values: dict[str, list[float]] = {m: [] for m in RAGAS_METRIC_IDS}
    for col, metric_id in col_map.items():
        if col in df.columns:
            vals = [float(v) for v in df[col].tolist() if v is not None and not _is_nan(v)]
            if vals:
                per_metric_values[metric_id] = vals
                scores[metric_id] = sum(vals) / len(vals)

    per_sample = []
    for index, row in enumerate(enriched):
        sample_scores = {}
        for col, metric_id in col_map.items():
            if col in df.columns:
                val = df[col].tolist()[index]
                if val is not None and not _is_nan(val):
                    sample_scores[metric_id] = float(val)
        per_sample.append({
            "sample_index": index + 1,
            "sample_origin": "ragas_live",
            "id": row["id"],
            "question": row["question"],
            "reference": row["reference"],
            "response": row["response"],
            "retrieved_context_count": len(row["retrieved_contexts"]),
            "scores": sample_scores,
        })

    return {
        "execution_status": "executed",
        "framework": "ragas",
        "framework_version": _ragas_version(),
        "judge_model": judge_model,
        "sample_size": len(enriched),
        "scores": scores,
        "samples": per_sample,
        "reason": None,
    }


def _is_nan(value: Any) -> bool:
    try:
        return value != value  # NaN != NaN
    except Exception:  # noqa: BLE001
        return False


def _ragas_version() -> str | None:
    try:
        import ragas
        return ragas.__version__
    except Exception:  # noqa: BLE001
        return None


def _result(status: str, reason: str, scores: dict, samples: list) -> dict[str, Any]:
    return {
        "execution_status": status,
        "framework": "ragas",
        "framework_version": _ragas_version(),
        "sample_size": len(samples),
        "scores": scores,
        "samples": samples,
        "reason": reason,
    }
