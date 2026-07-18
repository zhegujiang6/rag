package com.smartdoc.evaluation.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.Instant;

/**
 * 评测结果详情 — 不冗余 user_id，通过 run_id 间接隔离。
 */
@Entity
@Table(name = "evaluation_results", indexes = {
        @Index(name = "idx_eres_run", columnList = "run_id"),
})
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EvaluationResult {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "run_id", nullable = false)
    private Long runId;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String question;

    @Column(name = "ground_truth_answer", columnDefinition = "TEXT")
    private String groundTruthAnswer;

    @Column(name = "generated_answer", columnDefinition = "TEXT")
    private String generatedAnswer;

    @Column(name = "retrieved_context", columnDefinition = "TEXT")
    private String retrievedContext;

    private Double contextPrecision;
    private Double contextRecall;
    private Double faithfulness;
    private Double answerRelevancy;
    private Double contextEntityRecall;

    @Column(name = "created_at")
    private Instant createdAt;
}
