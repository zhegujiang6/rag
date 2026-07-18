package com.smartdoc.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

/**
 * API 网关 — Spring Cloud Gateway 入口。
 *
 * <p>职责：
 * <ul>
 *   <li>统一入口 — 所有前端请求经网关路由到对应微服务</li>
 *   <li>JWT 鉴权 — 在 Gateway Filter 层验证 Token</li>
 *   <li>限流 — 基于 Redis 的令牌桶算法</li>
 *   <li>日志 — 记录所有请求 method/path/耗时/状态码</li>
 *   <li>CORS — 统一处理跨域</li>
 * </ul>
 *
 * <p>路由规则 (见 {@code RouteConfig})：
 * <pre>
 *   /api/v1/auth/**      → user-service:8081
 *   /api/v1/chat/**      → rag-service:8082
 *   /api/v1/search/**    → rag-service:8082
 *   /api/v1/documents/** → document-service:8083
 *   /api/v1/knowledge-bases/** → document-service:8083
 *   /api/v1/evaluation/** → evaluation-service:8084
 * </pre>
 */
@SpringBootApplication
@EnableDiscoveryClient
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
