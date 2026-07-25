package com.smartdoc.evaluation.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * 评测运行响应。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EvalRunResponse {

    private Long runId;
    private Long knowledgeBaseId;
    private int testCaseCount;
    private Map<String, Double> avgMetrics;
    private List<Map<String, Object>> details;
    private Instant createdAt;
}
