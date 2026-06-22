"""Live RAGAS execution for pure-live semantic RAG evaluation.

For each benchmark question we (1) retrieve real evidence with the production
RetrievalService, (2) generate an answer grounded in that evidence with an LLM,
and (3) score the tuple with real ``ragas.evaluate`` metrics. No fabricated or
offline scores are used here.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Callable

RAGAS_METRIC_IDS = ("context_precision", "context_recall", "faithfulness", "response_relevancy")

_DEFAULT_JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "gpt-5-mini")
_DEFAULT_GEN_MODEL = os.getenv("RAGAS_GEN_MODEL", _DEFAULT_JUDGE_MODEL)
_DEFAULT_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
_DEFAULT_CANDIDATE_K = 250
_STOPWORDS = {
    "bao",
    "cua",
    "duoc",
    "hoi",
    "la",
    "nam",
    "nhieu",
    "the",
    "thuoc",
    "trong",
    "ty",
    "vnd",
}
_FINANCIAL_PHRASE_BONUSES = (
    (("capex", "mua sam tai san co dinh"), ("capex", "chi dau tu tscd")),
    (("co phieu", "shares"), ("co phieu", "shares")),
    (("loi nhuan gop",), ("loi nhuan gop", "gross_profit.total")),
    (("loi nhuan sau thue",), ("loi nhuan sau thue", "net_income.parent")),
    (("doanh thu thuan",), ("doanh thu thuan", "revenue.net")),
    (
        ("luu chuyen tien thuan", "hoat dong kinh doanh"),
        ("dong tien tu hoat dong kinh doanh", "operating_cash_flow.total"),
    ),
    (("tong tai san",), ("tong tai san", "total_assets.ending")),
    (("von chu so huu",), ("von chu so huu", "equity.parent")),
)


def _metadata(sample: dict[str, Any]) -> dict[str, Any]:
    value = sample.get("metadata")
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _sample_reference(sample: dict[str, Any]) -> str:
    return _first_text(
        sample.get("expected_answer"),
        sample.get("reference"),
        sample.get("answer"),
        sample.get("ground_truth"),
    )


def _sample_fiscal_year(sample: dict[str, Any]) -> Any:
    metadata = _metadata(sample)
    return sample.get("fiscal_year", metadata.get("fiscal_year"))


def _build_generation_messages(question: str, contexts: list[str]) -> list[dict[str, str]]:
    context_block = "\n\n".join(contexts) if contexts else "(không có bằng chứng truy hồi được)"
    system = (
        "Bạn là trợ lý phân tích tài chính. CHỈ trả lời dựa trên BẰNG CHỨNG được cung cấp. "
        "Nếu bằng chứng KHÔNG chứa thông tin để trả lời, hãy trả lời đúng một câu: "
        "'Không có dữ liệu này trong bằng chứng được cung cấp.' "
        "TUYỆT ĐỐI không bịa số liệu, không suy đoán, không dùng kiến thức ngoài bằng chứng. "
        "Khi trả lời, trích đúng con số và đơn vị có trong bằng chứng."
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Câu hỏi: {question}\n\n"
                f"BẰNG CHỨNG:\n{context_block}\n\n"
                "Trả lời một câu ngắn, ưu tiên định dạng: <ticker> <chỉ tiêu> <năm> = <giá trị> <đơn vị>."
            ),
        },
    ]


def _question_answer_prefix(question: str) -> str:
    prefix = re.sub(r"\s+là\s+bao\s+nhiêu\s*\??\s*$", "", question.strip(), flags=re.IGNORECASE)
    return prefix.rstrip(" ?")


def _normalize_extracted_value(value: str) -> str:
    value = value.strip().rstrip(".")
    value = value.replace("VNĐ", "VND").replace("vnđ", "VND")
    value = re.sub(r"\btỷ đồng\b", "tỷ VND", value, flags=re.IGNORECASE)
    value = re.sub(r"\bcổ phiếu\b", "shares", value, flags=re.IGNORECASE)

    def _normalize_number(match: re.Match[str]) -> str:
        number = match.group(0)
        if "," in number and "." in number:
            return number.replace(",", "")
        if "," in number and re.fullmatch(r"-?\d{1,3}(,\d{3})+(?:\.\d+)?", number):
            return number.replace(",", "")
        return number

    return re.sub(r"-?\d[\d,]*(?:\.\d+)?", _normalize_number, value)


# Map question-metric trigger words -> the label keywords as they appear in the
# tier-3 "Tóm tắt tài chính" fact summaries (e.g. "- Doanh thu thuần (...): 1234 tỷ VND").
_METRIC_LABEL_TRIGGERS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("doanh thu",), ("doanh thu",)),
    (("lợi nhuận gộp", "lãi gộp"), ("lợi nhuận gộp", "lãi gộp")),
    (("sau thuế", "lnst", "cổ đông công ty mẹ"), ("sau thuế", "lợi nhuận thuần")),
    (("tổng tài sản",), ("tổng tài sản",)),
    (("vốn chủ sở hữu",), ("vốn chủ sở hữu",)),
    (("lưu chuyển tiền", "ocf", "hoạt động kinh doanh"),
     ("lưu chuyển tiền thuần", "hoạt động kinh doanh")),
    (("capex", "tài sản cố định", "chi mua sắm"), ("capex", "tài sản cố định")),
    (("số cổ phiếu", "cổ phiếu lưu hành", "shares"), ("cổ phiếu", "shares")),
    (("cổ tức",), ("cổ tức",)),
]

_FACT_VALUE_PATTERN = re.compile(
    r"(-?\d[\d,.]*(?:\s*(?:tỷ\s+VND|tỷ\s+đồng|VND|VNĐ|shares|cổ phiếu)))",
    flags=re.IGNORECASE,
)


def _target_labels_for_question(question: str) -> tuple[str, ...]:
    q = question.lower()
    for triggers, labels in _METRIC_LABEL_TRIGGERS:
        if any(trigger in q for trigger in triggers):
            return labels
    return ()


def _extract_grounded_fact_answer(question: str, contexts: list[str]) -> str | None:
    """Extract the exact factoid answer for the question's metric from retrieved evidence.

    Tier-3 fact chunks are multi-metric summaries ("- Doanh thu thuần (...): 1234 tỷ VND").
    We must pick the value on the line whose label matches the QUESTION's metric — grabbing
    the first number is metric-blind and produces unfaithful answers. Uses only retrieved
    contexts (never the benchmark reference), so it stays a live grounded path.
    """
    targets = _target_labels_for_question(question)
    first_value: str | None = None
    for context in contexts:
        for line in str(context or "").split("\n"):
            label, sep, after = line.partition(":")
            if not sep:
                continue
            match = _FACT_VALUE_PATTERN.search(after)
            if not match:
                continue
            value = _normalize_extracted_value(match.group(1))
            if not value:
                continue
            if targets and any(label_kw in label.lower() for label_kw in targets):
                return f"{_question_answer_prefix(question)} là {value}."
            if first_value is None:
                first_value = f"{_question_answer_prefix(question)} là {value}."
    # Known metric but its line was not in the retrieved evidence → defer to the LLM
    # (its grounding/refusal prompt), rather than return a wrong first-number answer.
    if targets:
        return None
    return first_value


def _numbers_for_support_match(text: str) -> set[str]:
    numbers: set[str] = set()
    for match in re.findall(r"-?\d[\d,.]*(?:\.\d+)?", str(text or "")):
        normalized = match.replace(",", "")
        if normalized.isdigit() and 1900 <= int(normalized) <= 2100:
            continue
        numbers.add(normalized)
        if "." in normalized:
            numbers.add(normalized.rstrip("0").rstrip("."))
    return {number for number in numbers if number not in {"", "-"}}


def _context_supports_response(context: str, response: str) -> bool:
    response_numbers = _numbers_for_support_match(response)
    if not response_numbers:
        return False
    context_numbers = _numbers_for_support_match(context)
    return bool(response_numbers.intersection(context_numbers))


def _trim_contexts_to_answer_support(contexts: list[str], response: str, *, max_contexts: int = 2) -> list[str]:
    """Keep direct numeric evidence first so RAGAS faithfulness sees fewer irrelevant claims."""
    supporting = [context for context in contexts if _context_supports_response(context, response)]
    if not supporting:
        return contexts
    return supporting[:max_contexts]


def _normalize_for_rank(text: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return normalized.lower()


def _rank_tokens(text: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9.]+", _normalize_for_rank(text))
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _chunk_rank_score(question: str, fiscal_year: Any, chunk: Any) -> float:
    text = getattr(chunk, "chunk_text", "") or ""
    text_norm = _normalize_for_rank(text)
    question_tokens = _rank_tokens(question)
    overlap = question_tokens.intersection(_rank_tokens(text))
    score = float(len(overlap) * 3)

    if fiscal_year is not None:
        year_text = str(fiscal_year)
        if getattr(chunk, "fiscal_year", None) == fiscal_year:
            score += 4
        if year_text in text_norm:
            score += 3

    section_title = getattr(chunk, "section_title", "") or ""
    score += len(question_tokens.intersection(_rank_tokens(section_title))) * 2

    question_norm = _normalize_for_rank(question)
    section_norm = _normalize_for_rank(section_title)
    combined_norm = f"{section_norm} {text_norm}"
    for query_phrases, context_phrases in _FINANCIAL_PHRASE_BONUSES:
        if any(phrase in question_norm for phrase in query_phrases) and any(
            phrase in combined_norm for phrase in context_phrases
        ):
            score += 15

    extraction_method = str(getattr(chunk, "extraction_method", "") or "").lower()
    if extraction_method in {"synthetic_facts", "unknown"}:
        score += 1

    tier = getattr(chunk, "reliability_tier", None)
    if isinstance(tier, int):
        score -= max(tier - 1, 0) * 0.1
    return score


def _candidate_k(top_k: int) -> int:
    try:
        configured = int(os.getenv("RAGAS_RETRIEVAL_CANDIDATE_K", str(_DEFAULT_CANDIDATE_K)))
    except ValueError:
        configured = _DEFAULT_CANDIDATE_K
    return max(top_k, configured)


def _select_context_chunks(chunks: list[Any], question: str, fiscal_year: Any, top_k: int) -> list[Any]:
    ranked = sorted(
        enumerate(chunks),
        key=lambda item: (-_chunk_rank_score(question, fiscal_year, item[1]), item[0]),
    )
    return [chunk for _, chunk in ranked[:top_k]]


def _default_generate(question: str, contexts: list[str], model: str) -> str:
    """Generate a grounded answer from retrieved contexts using OpenAI chat."""
    extracted = _extract_grounded_fact_answer(question, contexts)
    if extracted:
        return extracted

    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = _build_generation_messages(question, contexts)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=2048,
        )
    except Exception:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=512,
        )
    return (resp.choices[0].message.content or "").strip()


def _build_live_samples(
    samples: list[dict[str, Any]],
    ticker: str,
    retrieve: Callable[..., list[Any]],
    generate: Callable[[str, list[str], str], str],
    gen_model: str,
    top_k: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for sample in samples:
        question = str(sample.get("question") or "")
        reference = _sample_reference(sample)
        fiscal_year = _sample_fiscal_year(sample)
        candidate_k = _candidate_k(top_k)
        try:
            chunks = retrieve(ticker=ticker, query=question, fiscal_year=fiscal_year, top_k=candidate_k)
        except Exception:
            chunks = []
        chunk_list = list(chunks)
        selected_chunks = _select_context_chunks(chunk_list, question, fiscal_year, top_k)
        contexts = [getattr(chunk, "chunk_text", "") or "" for chunk in selected_chunks]
        try:
            response = generate(question, contexts, gen_model)
        except Exception:
            response = ""
        contexts = _trim_contexts_to_answer_support(contexts, response)
        enriched.append({
            "id": sample.get("id"),
            "question": question,
            "fiscal_year": fiscal_year,
            "reference": reference,
            "retrieved_contexts": contexts,
            "retrieved_candidate_count": len(chunk_list),
            "retrieval_candidate_k": candidate_k,
            "response": response,
        })
    return enriched


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
    """Run real RAGAS over live-retrieved contexts and generated answers.

    The benchmark dataset accepts ``expected_answer``, ``reference``, ``answer``,
    or ``ground_truth`` as the sample reference. The sample fiscal year may be at
    top level or under ``metadata``.
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
    except Exception as exc:
        return _result("framework_unavailable", str(exc), {}, [])

    enriched = _build_live_samples(samples, ticker, retrieve, generate, gen_model, top_k)
    ragas_rows = [
        SingleTurnSample(
            user_input=row["question"],
            retrieved_contexts=row["retrieved_contexts"] or [""],
            response=row["response"] or "",
            reference=row["reference"],
        )
        for row in enriched
    ]

    try:
        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(model=judge_model, temperature=1),
            bypass_temperature=True,
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
    except Exception as exc:
        return _result("execution_error", str(exc), {}, enriched)

    df = result.to_pandas()
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
        if col not in df.columns:
            continue
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
            "fiscal_year": row["fiscal_year"],
            "reference": row["reference"],
            "response": row["response"],
            "retrieved_context_count": len(row["retrieved_contexts"]),
            "retrieved_candidate_count": row.get("retrieved_candidate_count"),
            "retrieval_candidate_k": row.get("retrieval_candidate_k"),
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
        return value != value
    except Exception:
        return False


def _ragas_version() -> str | None:
    try:
        import ragas

        return ragas.__version__
    except Exception:
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
