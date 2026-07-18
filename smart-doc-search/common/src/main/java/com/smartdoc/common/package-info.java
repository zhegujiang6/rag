/**
 * 公共模块 (smart-doc-common)
 *
 * <p>所有微服务共享的基础类：
 * <ul>
 *   <li>{@code dto} — 通用数据传输对象 (ApiResponse, PageResult, 基础请求/响应)</li>
 *   <li>{@code exception} — 全局异常定义 (BusinessException, ErrorCode 枚举)</li>
 *   <li>{@code util} — 工具类 (JwtUtils, HashUtils, 日期格式化)</li>
 *   <li>{@code constant} — 系统常量 (Redis Key 模式, 状态枚举)</li>
 *   <li>{@code config} — 公共配置 (Jackson 配置, 跨服务 Bean)</li>
 * </ul>
 */
package com.smartdoc.common;
