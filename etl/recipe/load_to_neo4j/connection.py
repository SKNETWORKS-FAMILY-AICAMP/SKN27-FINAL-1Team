# 로그 
import logging
logger = logging.getLogger(__name__)

# 패키지
import os
from dotenv import load_dotenv

from neo4j import GraphDatabase
from graphdatascience import GraphDataScience
# from langchain_ollama import OllamaEmbeddings


#####################################################################################
# 싱글톤 패턴 
#####################################################################################

class Singleton(type):
	_instances = {}

	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls)\
				.__call__(*args, **kwargs)
		return cls._instances[cls]


#####################################################################################
# 싱글톤 클래스 상속받아서 neo4j 연결 객체 생성
#####################################################################################
class Neo4j_Connection(metaclass=Singleton):
    '''
    Neo4j DB 연결 객체 생성 및 관련 내장 클래스 정의
    - 클래스는 싱글톤으로 구성
    - 객체에는 공통으로 사용하는 변수와 매서드만 우선적으로 내장한다. (close, 초기화 등...)
    '''
    def __init__(self, uri, user, password, embedding_model="qwen3-embedding:0.6b"):
        '''
        생성 시점에 주소, 변수 등 로그인 관련 값들 받아와서 드라이버 생성하고 
        해당 부분에서 연결 체크까지 처리한다. 
        - 사용하는 임배딩 모델은 qwen3-embedding:0.6b 를 사용한다. 
        '''
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # self.embedding_model = OllamaEmbeddings(model=embedding_model)
        self.gds = GraphDataScience(uri, auth=(user, password))
        logger.info(f"Neo4j 연결 성공: {uri}")
        logger.info(f"임베딩 모델: {embedding_model}")

    def close(self):
        '''해당 메소드 실행해서 리소스를 놓아주기 위함'''
        self.driver.close()
        logger.info("Neo4j 드라이버 연결 해제 완료")


    def execute_query(self, query:str="", parameters:dict=None) -> list:
        '''
        session.run을 래핑해서 간단한 리스트 형태로 결과를 반환 시킴
        '''
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]


    def clear_database(self):
        """Neo4j의 모든 노드와 관계를 삭제"""
        with self.driver.session() as session:
            # MATCH (n): 모든 노드 선택
            # DETACH DELETE n: 노드와 연결된 모든 관계를 먼저 삭제한 후 노드 삭제
            # (DETACH 없이 DELETE하면 관계가 있는 노드는 삭제 불가)
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("=== 기존 데이터 삭제 완료! ===")

if __name__ == "__main__":

    # 단독 실행 시 기본 설정 
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(filename)s %(message)s", )
    load_dotenv()

    # 테스트 시작 
    logger.info("=== Neo4j 연결 테스트 ===")

    conn1 = Neo4j_Connection(
        uri=os.getenv("NEO4J_URI"),
        user=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD"),
        # embedding_model=os.getenv("NEO4J_EMBEDDING_MODEL")
    )

    conn2 = Neo4j_Connection(
        uri=os.getenv("NEO4J_URI"),
        user=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD"),
        # embedding_model=os.getenv("NEO4J_EMBEDDING_MODEL")
    )

    logger.info("첫 번째 연결: %s", conn1)
    logger.info("두 번째 연결: %s", conn2)

    try: 
        if conn1 is conn2:
            logger.info("같은 연결인가? %s", conn1 is conn2)
            logger.info("싱글톤 패턴 적용 완료: 동일한 연결을 재사용합니다.")

    except Exception as e:
        logger.error(f"Neo4j 연결 실패: {e}")
        raise e