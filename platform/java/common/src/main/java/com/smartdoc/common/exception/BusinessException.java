package com.smartdoc.common.exception;

import lombok.Getter;

/**
 * 业务异常 — 所有服务层抛出此异常，由全局异常处理器统一捕获。
 */
@Getter
public class BusinessException extends RuntimeException {

    private final int code;

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public BusinessException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.code = errorCode.getCode();
    }

    public BusinessException(ErrorCode errorCode, String detail) {
        super(errorCode.getMessage() + ": " + detail);
        this.code = errorCode.getCode();
    }
}
