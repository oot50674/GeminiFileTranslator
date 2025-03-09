# GeminiFileTranslator
![image](https://github.com/user-attachments/assets/75d7207a-38b5-4875-9f3c-ff1583c70b5a)



## 소개

파일명 번역기는 Google Gemini API를 활용하여 파일명과 폴더명을 다양한 언어로 번역해주는 데스크톱 애플리케이션입니다. 한국어, 영어, 일본어 간의 번역을 지원하며, 사용자 정의 프롬프트를 통해 번역 품질을 조정할 수 있습니다.

## 주요 기능

- 파일명 및 폴더명 일괄 번역 (한국어, 영어, 일본어 지원)
- 하위 폴더 포함 옵션
- 특정 확장자 제외 기능
- 사용자 정의 번역 프롬프트 설정
- 번역 전 미리보기 및 선택적 적용
- 번역 설정 저장 기능
- 배치 처리 및 API 요청 최적화

## 설치 방법

### 실행 파일 다운로드 (권장)

1. [릴리스 페이지](https://github.com/oot50674/GeminiFileTranslator/releases)에서 최신 버전의 `GeminiFileTranslator.exe` 파일을 다운로드합니다.
2. 다운로드한 실행 파일을 더블 클릭하여 실행합니다.


## 사용 방법

1. [Google AI Studio](https://aistudio.google.com/)에서 Google Gemini API 키를 발급받습니다 (무료 api로도 일반적인 사용에 충분합니다)
2. 애플리케이션을 실행하고 API 키를 입력합니다
3. 번역할 파일이 있는 폴더 경로를 지정합니다
4. 번역 설정을 조정합니다:
   - 번역 언어 선택 (한국어, 영어, 일본어)
   - 하위 폴더 포함 여부
   - 폴더명 번역 여부
   - 제외할 확장자 지정
   - 청크 크기 및 대기 시간 설정
5. "파일 가져오기" 버튼을 클릭하여 파일 목록을 불러옵니다
6. 번역할 파일을 선택합니다 (체크박스)
7. "번역하기" 버튼을 클릭하여 번역을 시작합니다
8. 번역 결과를 확인하고 "적용하기" 버튼을 클릭하여 파일명을 변경합니다

## 주의사항

- 파일명 변경은 되돌릴 수 없으므로 중요한 파일은 미리 백업하세요
- API 키는 안전하게 보관하고 공유하지 마세요
- 대량의 파일을 처리할 경우 API 사용량 제한에 주의하세요
- 윈도우에서 사용할 수 없는 특수문자는 자동으로 '_'로 대체됩니다

## 시스템 요구사항

- Windows 10 이상
- 인터넷 연결
- Google Gemini API 키

## 라이선스
이 프로젝트는 MIT 라이선스 하에 배포됩니다.
