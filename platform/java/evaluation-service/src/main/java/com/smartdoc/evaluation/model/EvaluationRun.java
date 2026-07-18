package com.smartdoc.evaluation.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 评测运行实体 — 冗余 user_id 用于权限校验。
 */
@Entity
@Table(name = "evaluation_runs", indexes = {
        @Index(name = "idx_erun_kb", columnList = "knowledge_base_id"),
        @Index(name = "idx_erun_user", columnList = "user_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EvaluationRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "knowledge_base_id", nullable = false)
    private Long knowledgeBaseId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "config_snapshot", columnDefinition = "JSON")
    private String configSnapshot;

    @Column(name = "test_case_count")
    private Integer testCaseCount;

    @Column(name = "avg_context_precision")
    private Double avgContextPrecision;

    @Column(name = "avg_context_recall")
    private Double avgContextRecall;

    @Column(name = "avg_faithfulness")
    private Double avgFaithfulness;

    @Column(name = "avg_answer_relevancy")
    private Double avgAnswerRelevancy;

    @Column(name = "avg_context_entity_recall")
    private Double avgContextEntityRecall;

    @Column(name = "created_at")
    private Instant createdAt;
}
