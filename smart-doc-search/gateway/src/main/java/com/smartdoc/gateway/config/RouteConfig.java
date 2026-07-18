package com.smartdoc.gateway.config;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 网关路由配置 — 定义 Path → Service 的映射关系。
 *
 * <p>服务名由 Nacos 注册中心解析（如 lb://user-service → 实际 IP:端口）。
 */
@Configuration
public class RouteConfig {

    @Bean
    public RouteLocator customRoutes(RouteLocatorBuilder builder) {
        return builder.routes()

                // ── 用户服务 (认证/授权) ──
                .route("user-service", r -> r
                        .path("/api/v1/auth/**", "/api/v1/users/**")
                        .filters(f -> f
                                .stripPrefix(0)
                                .addRequestHeader("X-Gateway-Source", "smart-doc-gateway")
                        )
                        .uri("lb://user-service"))

                // ── RAG 检索 & 对话 ──
                .route("rag-service-chat", r -> r
                        .path("/api/v1/chat/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://rag-service"))
                .route("rag-service-search", r -> r
                        .path("/api/v1/search/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://rag-service"))
                .route("rag-service-conv", r -> r
                        .path("/api/v1/conversations/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://rag-service"))
                .route("rag-service-feedback", r -> r
                        .path("/api/v1/feedback/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://rag-service"))

                // ── 文档管理 & 知识库 ──
                .route("document-service-docs", r -> r
                        .path("/api/v1/documents/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://document-service"))
                .route("document-service-kb", r -> r
                        .path("/api/v1/knowledge-bases/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://document-service"))
                .route("document-service-tags", r -> r
                        .path("/api/v1/tags/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://document-service"))

                // ── 评测服务 ──
                .route("evaluation-service", r -> r
                        .path("/api/v1/evaluation/**")
                        .filters(f -> f.stripPrefix(0))
                        .uri("lb://evaluation-service"))

                .build();
    }
}
