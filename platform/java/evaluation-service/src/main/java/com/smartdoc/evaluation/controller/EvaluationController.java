package com.smartdoc.evaluation.controller;

import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.evaluation.dto.EvalRunRequest;
import com.smartdoc.evaluation.dto.EvalRunResponse;
import com.smartdoc.evaluation.service.EvaluationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * RAGAS 评测控制器。
 */
@RestController
@RequestMapping("/api/v1/evaluation")
@RequiredArgsConstructor
@Tag(name = "评测管理", description = "RAGAS 评测执行 & 结果查询")
public class EvaluationController {

    private final EvaluationService evaluationService;

    private Long getUserId() {
        Long userId = UserContext.getUserId();
        if (userId == null) throw new BusinessException(ErrorCode.UNAUTHORIZED);
        return userId;
    }

    @PostMapping("/run")
    @Operation(summary = "执行 RAGAS 评测")
    public ApiResponse<EvalRunResponse> runEvaluation(@RequestBody EvalRunRequest request) {
        return ApiResponse.ok(evaluationService.run(request, getUserId()));
    }

    @GetMapping("/runs")
    @Operation(summary = "评测历史列表")
    public ApiResponse<List<EvalRunResponse>> listRuns(
            @RequestParam(required = false) Long kbId) {
        return ApiResponse.ok(evaluationService.list(kbId, getUserId()));
    }

    @GetMapping("/runs/{runId}")
    @Operation(summary = "评测详情 (含每个测试用例的结果)")
    public ApiResponse<EvalRunResponse> getRunDetail(@PathVariable Long runId) {
        return ApiResponse.ok(evaluationService.get(runId, getUserId()));
    }
}
