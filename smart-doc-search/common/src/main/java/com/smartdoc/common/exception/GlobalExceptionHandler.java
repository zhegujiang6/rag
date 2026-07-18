package com.smartdoc.common.exception;

import com.smartdoc.common.dto.ApiResponse;
import jakarta.validation.ConstraintViolationException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常处理器 — 统一将异常转换为 ApiResponse。
 * <p>所有微服务的 Controller 需扫描此包以激活。
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /** 业务异常 */
    @ExceptionHandler(BusinessException.class)
    public ApiResponse<Void> handleBusiness(BusinessException e) {
        log.warn("业务异常: [{}] {}", e.getCode(), e.getMessage());
        return ApiResponse.fail(e.getCode(), e.getMessage());
    }

    /** 参数校验异常 (JSR-303) */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(err -> err.getField() + ": " + err.getDefaultMessage())
                .reduce((a, b) -> a + "; " + b)
                .orElse("参数校验失败");
        return ApiResponse.fail(ErrorCode.PARAM_INVALID.getCode(), msg);
    }

    /** 路径/查询参数校验异常 */
    @ExceptionHandler(ConstraintViolationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> handleConstraintViolation(ConstraintViolationException e) {
        return ApiResponse.fail(ErrorCode.PARAM_INVALID.getCode(), e.getMessage());
    }

    /** 兜底：未知异常 */
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiResponse<Void> handleUnknown(Exception e) {
        log.error("未知异常", e);
        return ApiResponse.fail(ErrorCode.UNKNOWN_ERROR.getCode(), "服务器内部错误");
    }
}
