package com.smartdoc.common.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 统一 API 响应体。
 * <p>所有微服务的 Controller 返回此格式，前端统一解析。
 *
 * @param <T> 数据类型
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ApiResponse<T> {

    /** 业务状态码 (0=成功) */
    private int code;

    /** 提示信息 */
    private String message;

    /** 响应数据 */
    private T data;

    /** 响应时间戳 */
    @Builder.Default
    private Instant timestamp = Instant.now();

    /** 请求追踪 ID (用于链路追踪) */
    private String traceId;

    // ── 工厂方法 ──

    public static <T> ApiResponse<T> ok(T data) {
        return ApiResponse.<T>builder().code(0).message("success").data(data).build();
    }

    public static <T> ApiResponse<T> ok(String message, T data) {
        return ApiResponse.<T>builder().code(0).message(message).data(data).build();
    }

    public static <T> ApiResponse<T> fail(int code, String message) {
        return ApiResponse.<T>builder().code(code).message(message).build();
    }

    public static <T> ApiResponse<T> fail(String message) {
        return ApiResponse.<T>builder().code(500).message(message).build();
    }
}
