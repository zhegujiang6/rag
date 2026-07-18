package com.smartdoc.user.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * Token 刷新请求 DTO。
 */
@Data
public class TokenRefreshRequest {

    @NotBlank(message = "Refresh Token 不能为空")
    private String refreshToken;
}
