package com.smartdoc.user.controller;

import com.smartdoc.common.dto.ApiResponse;
import com.smartdoc.user.dto.LoginRequest;
import com.smartdoc.user.dto.LoginResponse;
import com.smartdoc.user.dto.RegisterRequest;
import com.smartdoc.user.dto.TokenRefreshRequest;
import com.smartdoc.user.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 认证控制器。
 */
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
@Tag(name = "认证管理", description = "用户注册、登录、Token 管理")
public class AuthController {

    private final AuthService authService;

    @PostMapping("/register")
    @Operation(summary = "用户注册")
    public ApiResponse<LoginResponse> register(@Valid @RequestBody RegisterRequest request) {
        LoginResponse resp = authService.register(request);
        return ApiResponse.ok(resp);
    }

    @PostMapping("/login")
    @Operation(summary = "用户登录")
    public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        LoginResponse resp = authService.login(request);
        return ApiResponse.ok(resp);
    }

    @PostMapping("/refresh")
    @Operation(summary = "刷新 Access Token")
    public ApiResponse<LoginResponse> refresh(@Valid @RequestBody TokenRefreshRequest request) {
        LoginResponse resp = authService.refresh(request.getRefreshToken());
        return ApiResponse.ok(resp);
    }

    @PostMapping("/logout")
    @Operation(summary = "登出 (Token 加入黑名单)")
    public ApiResponse<Void> logout(@RequestHeader("Authorization") String authHeader) {
        authService.logout(authHeader);
        return ApiResponse.ok(null);
    }
}
