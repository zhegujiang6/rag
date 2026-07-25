package com.smartdoc.evaluation.dto;

import lombok.Data;

/**
 * 评测执行请求。
 */
@Data
public class EvalRunRequest {

    private Long knowledgeBaseId;
    private int testCount = 10;
    private int topK = 5;
    private boolean quickMode = true;
    private String datasetPath;   // 可选：使用已保存的测试集
}
