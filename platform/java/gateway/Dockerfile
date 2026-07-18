FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

# 从 Maven 构建产物复制 JAR
COPY target/gateway-*.jar app.jar

# JVM 参数优化
ENV JAVA_OPTS="-Xms256m -Xmx512m -XX:+UseZGC -XX:+ZGenerational"

EXPOSE 8080

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
