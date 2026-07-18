package com.smartdoc.evaluation.service;

import com.smartdoc.evaluation.dto.EvalRunRequest;
import com.smartdoc.evaluation.dto.EvalRunResponse;
import java.util.List;

public interface EvaluationService {
    EvalRunResponse run(EvalRunRequest request, Long userId);
    List<EvalRunResponse> list(Long knowledgeBaseId, Long userId);
    EvalRunResponse get(Long runId, Long userId);
}
