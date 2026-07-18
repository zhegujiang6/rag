package com.smartdoc.evaluation.repository;

import com.smartdoc.evaluation.model.EvaluationRun;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 评测运行 Repository — 按 userId 隔离。
 */
@Repository
public interface EvaluationRunRepository extends JpaRepository<EvaluationRun, Long> {

    /** 获取用户所有评测记录 */
    List<EvaluationRun> findByUserIdOrderByCreatedAtDesc(Long userId);

    /** 按知识库和 userId 查询 */
    List<EvaluationRun> findByKnowledgeBaseIdAndUserIdOrderByCreatedAtDesc(Long kbId, Long userId);

    /** 按 ID 和 userId 验证所有权 */
    java.util.Optional<EvaluationRun> findByIdAndUserId(Long id, Long userId);
}
