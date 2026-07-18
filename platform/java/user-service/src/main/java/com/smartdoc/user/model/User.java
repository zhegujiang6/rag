package com.smartdoc.user.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

/**
 * 用户实体。
 */
@Entity
@Table(name = "users")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(length = 100)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private Role role;

    @Column(name = "created_at")
    private Instant createdAt;

    /** 用户角色 */
    public enum Role {
        ADMIN,   // 管理员 — 全部权限
        USER,    // 普通用户 — 管理自己的知识库
        VIEWER,  // 只读用户 — 仅查看
    }
}
