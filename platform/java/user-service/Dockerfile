FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

COPY target/user-service-*.jar app.jar

ENV JAVA_OPTS="-Xms256m -Xmx512m -XX:+UseZGC -XX:+ZGenerational"

EXPOSE 8081

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
