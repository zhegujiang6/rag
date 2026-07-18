package com.smartdoc.evaluation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.cloud.openfeign.EnableFeignClients;

/**
 * RAGAS 评测服务入口。
 *
 * <p>职责：
 * <ul>
 *   <li>评测执行 — 对指定知识库运行 RAGAS 评测</li>
 *   <li>指标计算 — Context Precision/Recall, Faithfulness, Answer Relevancy, Entity Recall</li>
 *   <li>测试数据集管理 — CRUD + 导入/导出</li>
 *   <li>A/B 对比评测 — 同一数据集对比不同检索配置</li>
 *   <li>报告生成 — PDF/Excel 导出</li>
 * </ul>
 *
 * <p>通过 Feign 调用 rag-service 获取检索结果，不直接操作 ChromaDB。</p>
 *
 * <p>API 端点：
 * <pre>
 *   POST /api/v1/evaluation/run        — 执行评测
 *   GET  /api/v1/evaluation/runs       — 评测历史
 *   GET  /api/v1/evaluation/runs/{id}  — 评测详情
 *   POST /api/v1/evaluation/datasets   — 创建测试集
 *   GET  /api/v1/evaluation/datasets   — 测试集列表
 * </pre>
 */
@SpringBootApplication(scanBasePackages = {"com.smartdoc.evaluation", "com.smartdoc.common"})
@EnableDiscoveryClient
@EnableFeignClients(basePackages = "com.smartdoc.evaluation.client")
public class EvaluationServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvaluationServiceApplication.class, args);
    }
}
