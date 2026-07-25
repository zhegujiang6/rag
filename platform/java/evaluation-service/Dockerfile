FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

COPY target/evaluation-service-*.jar app.jar

ENV JAVA_OPTS="-Xms256m -Xmx1g -XX:+UseZGC -XX:+ZGenerational"

EXPOSE 8084

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
