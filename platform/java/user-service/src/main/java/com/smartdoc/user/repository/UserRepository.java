package com.smartdoc.user.repository;

import com.smartdoc.user.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

/**
 * 用户数据访问层。
 */
@Repository
public interface UserRepository extends JpaRepository<User, Long> {

    /** 按用户名查找 */
    Optional<User> findByUsername(String username);

    /** 检查用户名是否已存在 */
    boolean existsByUsername(String username);
}
