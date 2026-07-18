package com.smartdoc.rag.repository;

import com.smartdoc.rag.model.Conversation;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 对话 Repository — 按 userId 隔离。
 */
@Repository
public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    /** 获取用户所有对话（按更新时间倒序） */
    List<Conversation> findByUserIdOrderByUpdatedAtDesc(Long userId);

    /** 按 ID 和 userId 查找（权限校验） */
    java.util.Optional<Conversation> findByIdAndUserId(Long id, Long userId);
}
