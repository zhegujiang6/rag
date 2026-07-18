package com.smartdoc.document;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 文档与知识库服务入口。
 *
 * <p>职责：
 * <ul>
 *   <li>文件上传 — 保存到 MinIO，异步处理管道</li>
 *   <li>网页导入 — URL 爬取 → 解析 → 入库</li>
 *   <li>文档 CRUD — 查询、删除（级联清理向量+文件）</li>
 *   <li>知识库 CRUD — 创建、删除（清理集合+关联）</li>
 *   <li>文档→知识库关联 — 多对多关系管理</li>
 *   <li>文档处理管道 — 解析→分割→向量化→标签 (RocketMQ 异步)</li>
 *   <li>标签管理 — 手动标签 + AI 自动标签</li>
 *   <li>BM25 索引 — 增量更新</li>
 * </ul>
 *
 * <p>API 端点：
 * <pre>
 *   POST   /api/v1/documents/upload          — 上传文档
 *   POST   /api/v1/documents/import-url      — 网页导入
 *   GET    /api/v1/documents                  — 文档列表
 *   GET    /api/v1/documents/{id}             — 文档详情
 *   DELETE /api/v1/documents/{id}             — 删除文档
 *   GET    /api/v1/documents/{id}/status      — 处理进度
 *   POST   /api/v1/knowledge-bases            — 创建知识库
 *   GET    /api/v1/knowledge-bases            — 知识库列表
 *   DELETE /api/v1/knowledge-bases/{id}       — 删除知识库
 *   POST   /api/v1/knowledge-bases/{id}/documents — 添加文档
 *   DELETE /api/v1/knowledge-bases/{id}/documents/{docId} — 移除文档
 *   POST   /api/v1/documents/{id}/tags        — 添加标签
 *   DELETE /api/v1/documents/{id}/tags/{tag}  — 删除标签
 * </pre>
 */
@SpringBootApplication(scanBasePackages = {"com.smartdoc.document", "com.smartdoc.common"})
@EnableDiscoveryClient
@EnableScheduling
public class DocumentServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentServiceApplication.class, args);
    }
}
