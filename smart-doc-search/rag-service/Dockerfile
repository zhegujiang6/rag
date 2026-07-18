FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

COPY target/rag-service-*.jar app.jar

# RAG 服务需要更多内存 (检索管线 + LLM 流式处理)
ENV JAVA_OPTS="-Xms512m -Xmx2g -XX:+UseZGC -XX:+ZGenerational"

EXPOSE 8082

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
