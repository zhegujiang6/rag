package com.smartdoc.evaluation.service.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.evaluation.dto.EvalRunRequest;
import com.smartdoc.evaluation.dto.EvalRunResponse;
import com.smartdoc.evaluation.model.EvaluationRun;
import com.smartdoc.evaluation.repository.EvaluationRunRepository;
import com.smartdoc.evaluation.service.EvaluationService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class EvaluationServiceImpl implements EvaluationService {
    private final EvaluationRunRepository repository;
    private final ObjectMapper objectMapper;
    @Override @Transactional
    public EvalRunResponse run(EvalRunRequest request, Long userId) {
        if (request.getKnowledgeBaseId() == null || request.getKnowledgeBaseId() <= 0 || request.getTestCount() <= 0) throw new BusinessException(ErrorCode.PARAM_INVALID);
        EvaluationRun run = repository.save(EvaluationRun.builder().knowledgeBaseId(request.getKnowledgeBaseId()).userId(userId)
                .configSnapshot(toJson(request)).testCaseCount(request.getTestCount()).avgContextPrecision(0D).avgContextRecall(0D)
                .avgFaithfulness(0D).avgAnswerRelevancy(0D).avgContextEntityRecall(0D).createdAt(Instant.now()).build());
        return toResponse(run);
    }
    @Override @Transactional(readOnly = true)
    public List<EvalRunResponse> list(Long knowledgeBaseId, Long userId) {
        List<EvaluationRun> runs = knowledgeBaseId == null ? repository.findByUserIdOrderByCreatedAtDesc(userId) : repository.findByKnowledgeBaseIdAndUserIdOrderByCreatedAtDesc(knowledgeBaseId, userId);
        return runs.stream().map(this::toResponse).toList();
    }
    @Override @Transactional(readOnly = true)
    public EvalRunResponse get(Long runId, Long userId) { return toResponse(repository.findByIdAndUserId(runId, userId).orElseThrow(() -> new BusinessException(ErrorCode.EVAL_RUN_NOT_FOUND))); }
    private String toJson(EvalRunRequest request) { try { return objectMapper.writeValueAsString(request); } catch (JsonProcessingException e) { throw new BusinessException(ErrorCode.PARAM_INVALID); } }
    private EvalRunResponse toResponse(EvaluationRun run) {
        Map<String, Double> metrics = new LinkedHashMap<>();
        metrics.put("context_precision", run.getAvgContextPrecision()); metrics.put("context_recall", run.getAvgContextRecall()); metrics.put("faithfulness", run.getAvgFaithfulness()); metrics.put("answer_relevancy", run.getAvgAnswerRelevancy()); metrics.put("context_entity_recall", run.getAvgContextEntityRecall());
        return EvalRunResponse.builder().runId(run.getId()).knowledgeBaseId(run.getKnowledgeBaseId()).testCaseCount(run.getTestCaseCount()).avgMetrics(metrics).createdAt(run.getCreatedAt()).build();
    }
}
