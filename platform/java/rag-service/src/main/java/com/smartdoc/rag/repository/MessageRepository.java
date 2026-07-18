package com.smartdoc.rag.repository;

import com.smartdoc.rag.model.Message;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * 消息 Repository — 按 userId 隔离。
 */
@Repository
public interface MessageRepository extends JpaRepository<Message, Long> {

    /** 获取对话内所有消息 + userId 校验 */
    List<Message> findByConversationIdAndUserIdOrderByCreatedAtAsc(Long conversationId, Long userId);

    /** 按 ID 和 userId 查找 */
    java.util.Optional<Message> findByIdAndUserId(Long id, Long userId);
}
