-- MySQL dump 10.13  Distrib 8.0.45, for macos26.2 (arm64)
--
-- Host: 127.0.0.1    Database: makemystay
-- ------------------------------------------------------
-- Server version	8.0.45-0ubuntu0.24.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `payments`
--

DROP TABLE IF EXISTS `payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `amount` decimal(10,2) NOT NULL,
  `currency` varchar(10) NOT NULL,
  `payment_type` varchar(50) NOT NULL,
  `status` enum('pending','success','failed','expired') NOT NULL,
  `order_id` varchar(100) NOT NULL,
  `payment_id` varchar(100) DEFAULT NULL,
  `signature` varchar(255) DEFAULT NULL,
  `payer_name` varchar(100) DEFAULT NULL,
  `payer_email` varchar(150) DEFAULT NULL,
  `payer_phone` varchar(15) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_payments_order_id` (`order_id`),
  KEY `ix_payments_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payments`
--

LOCK TABLES `payments` WRITE;
/*!40000 ALTER TABLE `payments` DISABLE KEYS */;
INSERT INTO `payments` VALUES (1,1.00,'INR','manual','pending','order_STQSrsHk2ilZXr',NULL,NULL,'mahes','quickpay@makemystay.ai','9790341157','2026-03-20 09:11:28','2026-03-20 09:11:28'),(2,1.00,'INR','manual','pending','order_STQV8bFJBAW4Mu',NULL,NULL,'ma','quickpay@makemystay.ai','9790341157','2026-03-20 09:13:37','2026-03-20 09:13:37'),(3,2000.00,'INR','manual','pending','order_STQz12QUUusHuC',NULL,NULL,'Janavi','quickpay@makemystay.ai','9663375596','2026-03-20 09:41:54','2026-03-20 09:41:54'),(4,1.00,'INR','manual','success','order_STR4slq0IamBaZ','pay_STR5FGBE4FeeIr','eddc9bdc195dccf85f7afe68e81dd2704bbb69568fb1df25a3d7dbdaf34b20bc','g','quickpay@makemystay.ai','7032884779','2026-03-20 09:47:27','2026-03-20 09:48:04');
/*!40000 ALTER TABLE `payments` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-03-20 15:50:21
