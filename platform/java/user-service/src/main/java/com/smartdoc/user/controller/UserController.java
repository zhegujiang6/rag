package com.smartdoc.user.controller;

import com.smartdoc.common.context.UserContext;
import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.common.exception.BusinessException;
import com.smartdoc.common.exception.ErrorCode;
import com.smartdoc.user.dto.UserInfoResponse;
import com.smartdoc.user.model.User;
import com.smartdoc.user.repository.UserRepository;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 用户信息控制器。
 */
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
@Tag(name = "用户管理", description = "当前用户信息查询")
public class UserController {

    private final UserRepository userRepository;

    @GetMapping("/me")
    @Operation(summary = "获取当前登录用户信息")
    public ApiResponse<UserInfoResponse> getCurrentUser() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(ErrorCode.UNAUTHORIZED);
        }

        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        UserInfoResponse resp = UserInfoResponse.builder()
                .id(user.getId())
                .username(user.getUsername())
                .email(user.getEmail())
                .role(user.getRole().name())
                .createdAt(user.getCreatedAt())
                .build();

        return ApiResponse.ok(resp);
    }

    @GetMapping("/exists")
    @Operation(summary = "检查用户名是否已存在（注册时前端实时校验）")
    public ApiResponse<Boolean> checkUsernameExists(@RequestParam String username) {
        boolean exists = userRepository.existsByUsername(username);
        return ApiResponse.ok(exists);
    }
}
