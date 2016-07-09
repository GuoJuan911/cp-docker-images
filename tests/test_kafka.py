import os
import unittest
import utils
import time
import string
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(CURRENT_DIR, "fixtures", "debian", "kafka")
HEALTH_CHECK = "bash -c 'cub kafka-ready $ZOOKEEPER_CONNECT {brokers} 20 20 10 && echo PASS || echo FAIL'"
ZK_READY = "bash -c 'cub zk-ready {servers} 10 10 2 && echo PASS || echo FAIL'"
KAFKA_CHECK = "bash -c 'kafkacat -L -b {host}:{port} -J' "
KAFKA_SSL_CHECK = """kafkacat -X security.protocol=ssl \
      -X ssl.ca.location=/etc/kafka/secrets/snakeoil-ca-1.crt \
      -X ssl.certificate.location=/etc/kafka/secrets/kafkacat-ca1-signed.pem \
      -X ssl.key.location=/etc/kafka/secrets/kafkacat.client.key \
      -X ssl.key.password=confluent \
      -L -b {host}:{port} -J"""


class ConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        machine_name = os.environ["DOCKER_MACHINE_NAME"]
        cls.machine = utils.TestMachine(machine_name)

        # Create directories with the correct permissions for test with userid and external volumes.
        cls.machine.ssh("mkdir -p /tmp/kafka-config-kitchen-sink-test/data")
        cls.machine.ssh("sudo chown -R 12345 /tmp/kafka-config-kitchen-sink-test/data")

        # Copy SSL files.
        print cls.machine.ssh("mkdir -p /tmp/kafka-config-test/secrets")
        local_secrets_dir = os.path.join(FIXTURES_DIR, "secrets")
        cls.machine.scp_to_machine(local_secrets_dir, "/tmp/kafka-config-test")

        cls.cluster = utils.TestCluster("config-test", FIXTURES_DIR, "standalone-config.yml")
        cls.cluster.start()
        assert "PASS" in cls.cluster.run_command_on_service("zookeeper", ZK_READY.format(servers="localhost:2181"))

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        cls.machine.ssh("sudo rm -rf /tmp/kafka-config-kitchen-sink-test")
        cls.machine.ssh("sudo rm -rf /tmp/kafka-config-test/secrets")

    @classmethod
    def is_kafka_healthy_for_service(cls, service, num_brokers):
        output = cls.cluster.run_command_on_service(service, HEALTH_CHECK.format(brokers=num_brokers))
        assert "PASS" in output

    def test_required_config_failure(self):
        self.assertTrue("BROKER_ID is required." in self.cluster.service_logs("failing-config", stopped=True))
        self.assertTrue("ZOOKEEPER_CONNECT is required." in self.cluster.service_logs("failing-config-zk-connect", stopped=True))
        self.assertTrue("ADVERTISED_LISTENERS is required." in self.cluster.service_logs("failing-config-adv-listeners", stopped=True))
        # Deprecated props.
        self.assertTrue("ADVERTISED_HOST is deprecated. Please use ADVERTISED_LISTENERS instead." in self.cluster.service_logs("failing-config-adv-hostname", stopped=True))
        self.assertTrue("ADVERTISED_PORT is deprecated. Please use ADVERTISED_LISTENERS instead." in self.cluster.service_logs("failing-config-adv-port", stopped=True))
        self.assertTrue("PORT is deprecated. Please use ADVERTISED_LISTENERS instead." in self.cluster.service_logs("failing-config-port", stopped=True))
        self.assertTrue("HOST is deprecated. Please use ADVERTISED_LISTENERS instead." in self.cluster.service_logs("failing-config-host", stopped=True))
        # SSL
        self.assertTrue("SSL_KEYSTORE_FILENAME is required." in self.cluster.service_logs("failing-config-ssl-keystore", stopped=True))
        self.assertTrue("SSL_KEYSTORE_CREDENTIALS is required." in self.cluster.service_logs("failing-config-ssl-keystore-password", stopped=True))
        self.assertTrue("SSL_KEY_CREDENTIALS is required." in self.cluster.service_logs("failing-config-ssl-key-password", stopped=True))
        self.assertTrue("SSL_TRUSTSTORE_FILENAME is required." in self.cluster.service_logs("failing-config-ssl-truststore", stopped=True))
        self.assertTrue("SSL_TRUSTSTORE_CREDENTIALS is required." in self.cluster.service_logs("failing-config-ssl-truststore-password", stopped=True))

    def test_default_config(self):
        self.is_kafka_healthy_for_service("default-config", 1)
        props = self.cluster.run_command_on_service("default-config", "cat /etc/kafka/kafka.properties")
        expected = """broker.id=1
            advertised.listeners=PLAINTEXT://default-config:9092
            listeners=PLAINTEXT://0.0.0.0:9092
            log.dirs=/opt/kafka/data
            zookeeper.connect=zookeeper:2181/defaultconfig
            """
        self.assertEquals(props.translate(None, string.whitespace), expected.translate(None, string.whitespace))

    def test_default_logging_config(self):
        self.is_kafka_healthy_for_service("default-config", 1)

        log4j_props = self.cluster.run_command_on_service("default-config", "cat /etc/kafka/log4j.properties")
        expected_log4j_props = """log4j.rootLogger=INFO, stdout

            log4j.appender.stdout=org.apache.log4j.ConsoleAppender
            log4j.appender.stdout.layout=org.apache.log4j.PatternLayout
            log4j.appender.stdout.layout.ConversionPattern=[%d] %p %m (%c)%n


            log4j.logger.kafka.authorizer.logger=WARN, stdout
            log4j.logger.kafka.log.LogCleaner=INFO, stdout
            log4j.logger.kafka.producer.async.DefaultEventHandler=DEBUG, stdout
            log4j.logger.kafka.controller=TRACE, stdout
            log4j.logger.kafka.network.RequestChannel$=WARN, stdout
            log4j.logger.kafka.request.logger=WARN, stdout
            log4j.logger.state.change.logger=TRACE, stdout
            log4j.logger.kafka=INFO, stdout
            """
        self.assertEquals(log4j_props.translate(None, string.whitespace), expected_log4j_props.translate(None, string.whitespace))

        tools_log4j_props = self.cluster.run_command_on_service("default-config", "cat /etc/kafka/tools-log4j.properties")
        expected_tools_log4j_props = """log4j.rootLogger=WARN, stderr

            log4j.appender.stderr=org.apache.log4j.ConsoleAppender
            log4j.appender.stderr.layout=org.apache.log4j.PatternLayout
            log4j.appender.stderr.layout.ConversionPattern=[%d] %p %m (%c)%n
            log4j.appender.stderr.Target=System.err
            """
        self.assertEquals(tools_log4j_props.translate(None, string.whitespace), expected_tools_log4j_props.translate(None, string.whitespace))

    def test_full_config(self):
        self.is_kafka_healthy_for_service("full-config", 1)
        props = self.cluster.run_command_on_service("full-config", "cat /etc/kafka/kafka.properties")
        expected = """broker.id=1
                advertised.listeners=PLAINTEXT://full-config:9092
                listeners=PLAINTEXT://0.0.0.0:9092
                log.dirs=/opt/kafka/data
                zookeeper.connect=zookeeper:2181/fullconfig
                """
        self.assertEquals(props.translate(None, string.whitespace), expected.translate(None, string.whitespace))

    def test_full_logging_config(self):
        self.is_kafka_healthy_for_service("full-config", 1)

        log4j_props = self.cluster.run_command_on_service("full-config", "cat /etc/kafka/log4j.properties")
        expected_log4j_props = """log4j.rootLogger=WARN, stdout

            log4j.appender.stdout=org.apache.log4j.ConsoleAppender
            log4j.appender.stdout.layout=org.apache.log4j.PatternLayout
            log4j.appender.stdout.layout.ConversionPattern=[%d] %p %m (%c)%n


            log4j.logger.kafka.authorizer.logger=WARN, stdout
            log4j.logger.kafka.log.LogCleaner=INFO, stdout
            log4j.logger.kafka.producer.async.DefaultEventHandler=DEBUG, stdout
            log4j.logger.kafka.controller=WARN, stdout
            log4j.logger.kafka.network.RequestChannel$=WARN, stdout
            log4j.logger.kafka.request.logger=WARN, stdout
            log4j.logger.state.change.logger=TRACE, stdout
            log4j.logger.kafka.foo.bar=DEBUG, stdout
            log4j.logger.kafka=INFO, stdout
            """
        self.assertEquals(log4j_props.translate(None, string.whitespace), expected_log4j_props.translate(None, string.whitespace))

        tools_log4j_props = self.cluster.run_command_on_service("full-config", "cat /etc/kafka/tools-log4j.properties")
        expected_tools_log4j_props = """log4j.rootLogger=ERROR, stderr

            log4j.appender.stderr=org.apache.log4j.ConsoleAppender
            log4j.appender.stderr.layout=org.apache.log4j.PatternLayout
            log4j.appender.stderr.layout.ConversionPattern=[%d] %p %m (%c)%n
            log4j.appender.stderr.Target=System.err
            """
        self.assertEquals(tools_log4j_props.translate(None, string.whitespace), expected_tools_log4j_props.translate(None, string.whitespace))

    def test_volumes(self):
        self.is_kafka_healthy_for_service("external-volumes", 1)

    def test_random_user(self):
        self.is_kafka_healthy_for_service("random-user", 1)

    def test_kitchen_sink(self):
        self.is_kafka_healthy_for_service("kitchen-sink", 1)
        zk_props = self.cluster.run_command_on_service("kitchen-sink", "cat /etc/kafka/kafka.properties")
        expected = """broker.id=1
                advertised.listeners=PLAINTEXT://kitchen-sink:9092
                listeners=PLAINTEXT://0.0.0.0:9092
                log.dirs=/opt/kafka/data
                zookeeper.connect=zookeeper:2181/kitchensink
                """
        self.assertEquals(zk_props.translate(None, string.whitespace), expected.translate(None, string.whitespace))

    def test_ssl_config(self):
        self.is_kafka_healthy_for_service("ssl-config", 1)
        zk_props = self.cluster.run_command_on_service("ssl-config", "cat /etc/kafka/kafka.properties")
        expected = """broker.id=1
                advertised.listeners=SSL://ssl-config:9092
                listeners=SSL://0.0.0.0:9092
                log.dirs=/opt/kafka/data
                zookeeper.connect=zookeeper:2181/sslconfig

                ssl.keystore.password=confluent
                ssl.truststore.password=confluent
                ssl.keystore.location=/etc/kafka/secrets/kafka.broker1.keystore.jks
                ssl.key.password=confluent
                security.inter.broker.protocol=SSL
                ssl.truststore.location=/etc/kafka/secrets/kafka.broker1.truststore.jks
                """
        self.assertEquals(zk_props.translate(None, string.whitespace), expected.translate(None, string.whitespace))


class StandaloneNetworkingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cluster = utils.TestCluster("standalone-network-test", FIXTURES_DIR, "standalone-network.yml")
        cls.cluster.start()
        assert "PASS" in cls.cluster.run_command_on_service("zookeeper-bridge", ZK_READY.format(servers="localhost:2181"))
        assert "PASS" in cls.cluster.run_command_on_service("zookeeper-host", ZK_READY.format(servers="localhost:32181"))

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()

    @classmethod
    def is_kafka_healthy_for_service(cls, service, num_brokers):
        output = cls.cluster.run_command_on_service(service, HEALTH_CHECK.format(brokers=num_brokers))
        assert "PASS" in output

    def test_bridge_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-bridge", 1)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_CHECK.format(host="localhost", port=19092),
            host_config={'NetworkMode': 'host'})

        parsed_logs = json.loads(logs)
        self.assertEquals(1, len(parsed_logs["brokers"]))
        self.assertEquals(1, parsed_logs["brokers"][0]["id"])
        self.assertEquals("localhost:19092", parsed_logs["brokers"][0]["name"])

    def test_host_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-host", 1)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_CHECK.format(host="localhost", port=29092),
            host_config={'NetworkMode': 'host'})

        parsed_logs = json.loads(logs)
        self.assertEquals(1, len(parsed_logs["brokers"]))
        self.assertEquals(1, parsed_logs["brokers"][0]["id"])
        self.assertEquals("localhost:29092", parsed_logs["brokers"][0]["name"])


class ClusterBridgeNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        machine_name = os.environ["DOCKER_MACHINE_NAME"]
        cls.machine = utils.TestMachine(machine_name)

        # Copy SSL files.
        print cls.machine.ssh("mkdir -p /tmp/kafka-cluster-bridge-test/secrets")
        local_secrets_dir = os.path.join(FIXTURES_DIR, "secrets")
        cls.machine.scp_to_machine(local_secrets_dir, "/tmp/kafka-cluster-bridge-test")

        cls.cluster = utils.TestCluster("cluster-test", FIXTURES_DIR, "cluster-bridged.yml")
        cls.cluster.start()
        assert "PASS" in cls.cluster.run_command_on_service("zookeeper-1", ZK_READY.format(servers="zookeeper-1:2181,zookeeper-2:2181,zookeeper-3:2181"))

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        cls.machine.ssh("sudo rm -rf /tmp/kafka-cluster-bridge-test/secrets")

    def test_cluster_running(self):
        self.assertTrue(self.cluster.is_running())

    @classmethod
    def is_kafka_healthy_for_service(cls, service, num_brokers):
        output = cls.cluster.run_command_on_service(service, HEALTH_CHECK.format(brokers=num_brokers))
        assert "PASS" in output

    def test_bridge_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-1", 3)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_CHECK.format(host="kafka-1", port=9092),
            host_config={'NetworkMode': 'cluster-test_zk'})

        parsed_logs = json.loads(logs)
        self.assertEquals(3, len(parsed_logs["brokers"]))
        expected_brokers = [{"id": 1, "name": "kafka-1:9092"}, {"id": 2, "name": "kafka-2:9092"}, {"id": 3, "name": "kafka-3:9092"}]
        self.assertEquals(sorted(expected_brokers), sorted(parsed_logs["brokers"]))

    def test_ssl_bridge_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-ssl-1", 3)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_SSL_CHECK.format(host="kafka-ssl-1", port=9093),
            host_config={'NetworkMode': 'cluster-test_zk', 'Binds': ['/tmp/kafka-cluster-host-test/secrets:/etc/kafka/secrets']})

        parsed_logs = json.loads(logs)
        self.assertEquals(3, len(parsed_logs["brokers"]))
        expected_brokers = [{"id": 1, "name": "kafka-ssl-1:9093"}, {"id": 2, "name": "kafka-ssl-2:9093"}, {"id": 3, "name": "kafka-ssl-3:9093"}]
        self.assertEquals(sorted(expected_brokers), sorted(parsed_logs["brokers"]))


class ClusterHostNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        machine_name = os.environ["DOCKER_MACHINE_NAME"]
        cls.machine = utils.TestMachine(machine_name)

        # Copy SSL files.
        print cls.machine.ssh("mkdir -p /tmp/kafka-cluster-host-test/secrets")
        local_secrets_dir = os.path.join(FIXTURES_DIR, "secrets")
        cls.machine.scp_to_machine(local_secrets_dir, "/tmp/kafka-cluster-host-test")

        cls.cluster = utils.TestCluster("cluster-test", FIXTURES_DIR, "cluster-host.yml")
        cls.cluster.start()
        assert "PASS" in cls.cluster.run_command_on_service("zookeeper-1", ZK_READY.format(servers="localhost:22181,localhost:32181,localhost:42181"))

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        cls.machine.ssh("sudo rm -rf /tmp/kafka-cluster-host-test/secrets")

    def test_cluster_running(self):
        self.assertTrue(self.cluster.is_running())

    @classmethod
    def is_kafka_healthy_for_service(cls, service, num_brokers):
        output = cls.cluster.run_command_on_service(service, HEALTH_CHECK.format(brokers=num_brokers))
        assert "PASS" in output

    def test_host_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-1", 3)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_CHECK.format(host="localhost", port=19092),
            host_config={'NetworkMode': 'host'})

        parsed_logs = json.loads(logs)
        self.assertEquals(3, len(parsed_logs["brokers"]))
        expected_brokers = [{"id": 1, "name": "localhost:19092"}, {"id": 2, "name": "localhost:29092"}, {"id": 3, "name": "localhost:39092"}]
        self.assertEquals(sorted(expected_brokers), sorted(parsed_logs["brokers"]))

    def test_ssl_host_network(self):
        # Test from within the container
        self.is_kafka_healthy_for_service("kafka-ssl-1", 3)
        # Test from outside the container
        logs = utils.run_docker_command(
            image="confluentinc/kafkacat",
            command=KAFKA_SSL_CHECK.format(host="localhost", port=19093),
            host_config={'NetworkMode': 'host', 'Binds': ['/tmp/kafka-cluster-host-test/secrets:/etc/kafka/secrets']})

        parsed_logs = json.loads(logs)
        self.assertEquals(3, len(parsed_logs["brokers"]))
        expected_brokers = [{"id": 1, "name": "localhost:19093"}, {"id": 2, "name": "localhost:29093"}, {"id": 3, "name": "localhost:39093"}]
        self.assertEquals(sorted(expected_brokers), sorted(parsed_logs["brokers"]))
