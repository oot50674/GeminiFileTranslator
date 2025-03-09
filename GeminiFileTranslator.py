import sys
import os
import json
import logging
import unicodedata
import time  # 대기시간을 위한 time 모듈 추가
import google.generativeai as genai
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QLabel, QLineEdit, QPushButton, QTextEdit, QRadioButton, 
                           QButtonGroup, QFileDialog, QMessageBox, QProgressBar, QGroupBox,
                           QSplitter, QCheckBox, QTreeWidget, QTreeWidgetItem, QHeaderView,
                           QStyle)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QFont

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 번역을 위한 쓰레드 클래스
class TranslationThread(QThread):
    # 시그널 정의
    progress_signal = pyqtSignal(int, int)  # (현재 번역 중인 파일 인덱스, 전체 파일 수)
    result_signal = pyqtSignal(list)  # 번역 결과 리스트
    error_signal = pyqtSignal(str)  # 오류 메시지
    
    def __init__(self, api_key, filenames, language, chunk_size=10, delay_time=3, model_name="gemini-2.0-flash", custom_prompt=None):
        super().__init__()
        self.api_key = api_key
        self.filenames = filenames
        self.language = language
        self.chunk_size = chunk_size
        self.delay_time = delay_time
        self.model_name = model_name
        self.custom_prompt = custom_prompt
        self.templates = {
            'korean': """
# 파일명 번역 시스템 프롬프트
- 이것은 파일명 번역을 위한 AI 시스템입니다.
- 파일명의 의미를 정확하게 파악하여 한국어로 번역해주세요.
- 파일명에 사용할 수 없는 특수문자(/, \, :, *, ?, ", <, >, |)는 사용하지 마세요.
- 파일 확장자(.txt, .jpg 등)는 번역하지 않고 그대로 유지하세요.
- 번역된 파일명은 원래 파일명의 의미를 유지하면서도 한국어 사용자가 이해하기 쉽게 번역하세요.
- 파일명은 간단명료하게 유지하고, 불필요한 조사나 특수문자를 추가하지 마세요.
- 번역문 이외의 추가적인 설명이나 코멘트는 제외하고 순수 번역 텍스트만 제공하세요.

사용자 정의 프롬프트:
{custom_prompt}
""",
            'english': """
# File Name Translation System Prompt
- This is an AI system for translating file names.
- Please accurately understand and translate the meaning of file names into English.
- Do not use special characters that cannot be used in file names (/, \, :, *, ?, ", <, >, |).
- Do not translate file extensions (.txt, .jpg, etc.) and keep them as they are.
- Translate file names to be easily understood by English users while maintaining the original meaning.
- Keep file names simple and concise, without adding unnecessary articles or special characters.
- Provide only the translated text, excluding any additional explanations or comments.

Custom User Prompt:
{custom_prompt}
""",
            'japanese': """
# ファイル名翻訳システムプロンプト
- これはファイル名を翻訳するためのAIシステムです。
- ファイル名の意味を正確に理解し、日本語に翻訳してください。
- ファイル名に使用できない特殊文字(/, \, :, *, ?, ", <, >, |)は使用しないでください。
- ファイル拡張子(.txt, .jpg など)は翻訳せず、そのまま維持してください。
- 翻訳されたファイル名は、元のファイル名の意味を保ちながら、日本語ユーザーが理解しやすいように翻訳してください。
- ファイル名はシンプルで簡潔に保ち、不要な助詞や特殊文字を追加しないでください。
- 翻訳文以外の追加説明やコメントを除き、純粋な翻訳テキストのみを提供してください。

カスタムユーザープロンプト:
{custom_prompt}
"""
        }
    
    def run(self):
        try:
            # API 키 설정
            genai.configure(api_key=self.api_key)
            
            # 생성 설정
            generation_config = genai.types.GenerationConfig(temperature=0.8)
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # 번역 템플릿 선택 (사용자 정의 프롬프트를 기본 템플릿에 추가)
            base_template = self.templates.get(self.language.lower(), self.templates['korean'])
            template = base_template.format(custom_prompt=self.custom_prompt if self.custom_prompt else "사용자 정의 프롬프트가 없습니다.")
            
            # 결과 저장 리스트
            all_translations = []
            
            # 파일명 배열을 청크 크기에 맞게 나누기
            chunk_size = self.chunk_size
            filename_chunks = [self.filenames[i:i + chunk_size] for i in range(0, len(self.filenames), chunk_size)]
            
            # 각 청크별로 번역 처리
            for i, chunk in enumerate(filename_chunks):
                try:
                    # 진행 상황 전송
                    current_progress = i * chunk_size
                    self.progress_signal.emit(current_progress, len(self.filenames))
                    
                    # 청크 처리 사이에 설정된 시간만큼 대기 (첫 번째 청크는 대기 안함)
                    if i > 0:
                        logger.info(f"청크 처리 사이 {self.delay_time}초 대기 중... ({i}/{len(filename_chunks)})")
                        time.sleep(self.delay_time)
                    
                    # 파일명들을 개행으로 구분된 하나의 텍스트로 변환
                    input_text = "\n".join(chunk)
                    
                    # 번역 요청을 위한 메시지 배열 생성
                    messages = [
                        {"role": "user", "parts": [{"text": template + "\n\n" + input_text}]}
                    ]
                    
                    # Gemini API 호출
                    logger.info(f"Gemini API 요청 - 언어: {self.language}, 입력 길이: {len(input_text)}, 청크: {i+1}/{len(filename_chunks)}")
                    response = model.generate_content(messages)
                    
                    # 응답 텍스트 획득
                    translated_text = response.text.strip()
                    logger.info(f"배치 번역 완료. 응답 길이: {len(translated_text)}")
                    
                    # 번역된 결과를 줄별로 분리
                    translated_lines = translated_text.split('\n')
                    
                    # 원본 파일명과 번역된 파일명을 매핑
                    for j, original_name in enumerate(chunk):
                        if j < len(translated_lines):
                            translated_name = translated_lines[j].strip()
                            if translated_name:  # 빈 문자열이 아닌 경우만 추가
                                all_translations.append({
                                    'original': original_name,
                                    'translated': translated_name
                                })
                                
                                # 각 파일 번역 후 진행 상황 업데이트
                                self.progress_signal.emit(current_progress + j + 1, len(self.filenames))
                        else:
                            logger.warning(f"번역 결과 누락: {original_name}")
                    
                except Exception as e:
                    logger.error(f"파일명 청크 번역 중 오류 발생: {str(e)}", exc_info=True)
                    # 오류 발생 시 대기 시간을 늘리고 재시도 (추가 지연)
                    logger.info("API 오류 발생 - 10초 대기 후 다음 청크로 계속...")
                    time.sleep(10)
                    # 현재 청크에서 오류가 발생해도 계속 진행
                    continue
            
            # 최종 결과 전송
            if all_translations:
                logger.info(f"전체 파일명 번역 완료. 번역된 파일 수: {len(all_translations)}")
                self.result_signal.emit(all_translations)
            else:
                self.error_signal.emit("모든 파일명 번역에 실패했습니다.")
                
        except Exception as e:
            logger.exception(f"번역 처리 중 오류 발생: {str(e)}")
            self.error_signal.emit(f"번역 처리 중 오류 발생: {str(e)}")


# 파일명 변경을 위한 쓰레드 클래스
class RenameThread(QThread):
    progress_signal = pyqtSignal(int, int)  # (현재 처리 중인 파일 인덱스, 전체 파일 수)
    result_signal = pyqtSignal(list)  # 이름 변경 성공한 파일 목록
    error_signal = pyqtSignal(str)  # 오류 메시지
    
    def __init__(self, items_to_rename):
        super().__init__()
        self.items_to_rename = items_to_rename
    
    def run(self):
        # 이름 변경 성공한 항목 목록
        renamed_items = []
        total_items = len(self.items_to_rename)
        
        try:
            # 파일과 폴더를 구분
            files_to_rename = [item for item in self.items_to_rename if item['type'] == 'file']
            folders_to_rename = [item for item in self.items_to_rename if item['type'] == 'folder']
            
            # 폴더 구조의 깊이에 따라 정렬 (가장 깊은 폴더부터 처리)
            folders_to_rename.sort(key=lambda folder: folder['original_path'].count(os.sep), reverse=True)
            
            # 파일을 먼저 처리한 후 깊이순으로 정렬된 폴더를 처리
            items_to_process = files_to_rename + folders_to_rename
            
            # 이름 변경 처리
            for i, item in enumerate(items_to_process):
                try:
                    # 진행 상황 업데이트
                    self.progress_signal.emit(i+1, total_items)
                    
                    original_path = item['original_path']
                    new_name = item['new_name']
                    item_type = item['type']
                    
                    # 원본 경로와 새 경로 계산
                    directory = os.path.dirname(original_path)
                    new_path = os.path.join(directory, os.path.basename(new_name))
                    
                    # 이미 동일한 이름의 파일이 있는지 확인
                    if os.path.exists(new_path) and original_path != new_path:
                        logger.warning(f"이름 변경 실패 - 이미 존재하는 경로: {new_path}")
                        continue
                    
                    # 이름 변경 시도
                    try:
                        os.rename(original_path, new_path)
                        
                        # 로그 추가 (폴더 구조 추적을 위한 디버깅)
                        if item_type == 'folder':
                            logger.info(f"폴더 이름 변경: {original_path} -> {new_path} (깊이: {original_path.count(os.sep)})")
                        
                        # 성공 목록에 추가
                        renamed_items.append({
                            'original_path': original_path,
                            'new_path': new_path,
                            'type': item_type
                        })
                    except PermissionError:
                        logger.error(f"권한 오류: {original_path} - 파일이 사용 중이거나 권한이 없습니다.")
                    except FileNotFoundError:
                        logger.error(f"파일을 찾을 수 없음: {original_path}")
                    except OSError as e:
                        logger.error(f"OS 오류: {str(e)} - {original_path}")
                    
                    # 처리 간격
                    time.sleep(0.1)  # 시스템 과부하 방지
                    
                except Exception as e:
                    logger.error(f"파일 이름 변경 오류: {str(e)} - {original_path}")
            
            # 결과 신호 전송
            self.result_signal.emit(renamed_items)
            
        except Exception as e:
            self.error_signal.emit(str(e))
            logger.exception("이름 변경 스레드 오류")


# 메인 윈도우 클래스
class TranslationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 설정 초기화
        self.settings = QSettings("TranslationApp", "FileNameTranslator")
        
        # 앱 데이터 초기화
        self.selected_files = []
        self.translated_filenames = {}
        
        # UI 초기화
        self.init_ui()
        
        # 저장된 설정 불러오기
        self.load_settings()
    
    def init_ui(self):
        # 메인 윈도우 설정
        self.setWindowTitle('파일명 번역기')
        self.setGeometry(100, 100, 1200, 800)
        
        # 중앙 위젯 생성
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(central_widget)
        
        # API 키 입력 섹션
        api_key_group = QGroupBox("Google Gemini API 키")
        api_key_layout = QHBoxLayout()
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Google Gemini API 키를 입력하세요")
        self.api_key_input.setEchoMode(QLineEdit.Password)  # 입력 내용 숨기기
        
        self.save_api_key_btn = QPushButton("API 키 저장")
        self.save_api_key_btn.clicked.connect(self.save_api_key)
        
        api_key_layout.addWidget(QLabel("API 키:"))
        api_key_layout.addWidget(self.api_key_input, 1)
        api_key_layout.addWidget(self.save_api_key_btn)
        
        api_key_group.setLayout(api_key_layout)
        main_layout.addWidget(api_key_group)
        
        # 번역 설정 섹션
        translation_settings_group = QGroupBox("번역 설정")
        translation_settings_layout = QVBoxLayout()
        
        # AI 모델 설정
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("AI 모델:"))
        self.model_input = QLineEdit("gemini-2.0-flash")
        self.model_input.setPlaceholderText("예: gemini-2.0-flash, gemini-1.5-pro")
        model_layout.addWidget(self.model_input, 1)
        
        translation_settings_layout.addLayout(model_layout)
        
        # 사용자 프롬프트 설정
        prompt_group = QGroupBox("번역 프롬프트 (비워두면 기본값 사용)")
        prompt_layout = QVBoxLayout()
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("사용자 정의 프롬프트를 입력하세요. 비워두면 기본 프롬프트를 사용합니다.")
        self.prompt_input.setMaximumHeight(100)
        prompt_layout.addWidget(self.prompt_input)
        prompt_group.setLayout(prompt_layout)
        
        translation_settings_layout.addWidget(prompt_group)
        
        # 청크 크기 및 대기 시간 설정
        chunk_delay_layout = QHBoxLayout()
        
        # 청크 크기 설정
        chunk_size_layout = QHBoxLayout()
        chunk_size_layout.addWidget(QLabel("한 번에 처리할 파일 수:"))
        self.chunk_size_input = QLineEdit("10")
        self.chunk_size_input.setFixedWidth(50)
        chunk_size_layout.addWidget(self.chunk_size_input)
        chunk_size_layout.addWidget(QLabel("개"))
        
        # 대기 시간 설정
        delay_time_layout = QHBoxLayout()
        delay_time_layout.addWidget(QLabel("청크 간 대기 시간:"))
        self.delay_time_input = QLineEdit("3")
        self.delay_time_input.setFixedWidth(50)
        delay_time_layout.addWidget(self.delay_time_input)
        delay_time_layout.addWidget(QLabel("초"))
        
        chunk_delay_layout.addLayout(chunk_size_layout)
        chunk_delay_layout.addSpacing(20)
        chunk_delay_layout.addLayout(delay_time_layout)
        chunk_delay_layout.addStretch(1)
        
        translation_settings_layout.addLayout(chunk_delay_layout)
        
        # 제외할 확장자 설정 제거 (파일 경로 입력 섹션으로 통합)
        
        translation_settings_group.setLayout(translation_settings_layout)
        main_layout.addWidget(translation_settings_group)
        
        # 파일 경로 입력 섹션
        file_group = QGroupBox("파일 선택")
        file_layout = QVBoxLayout()
        
        # 경로 입력 및 버튼
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("파일이 위치한 경로를 입력하세요")
        
        self.browse_btn = QPushButton("찾아보기")
        self.browse_btn.clicked.connect(self.browse_directory)
        
        self.get_files_btn = QPushButton("파일 가져오기")
        self.get_files_btn.clicked.connect(self.get_files)
        
        path_layout.addWidget(QLabel("경로:"))
        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(self.browse_btn)
        path_layout.addWidget(self.get_files_btn)
        
        file_layout.addLayout(path_layout)
        
        # 제외 확장자 설정 (한 줄 전체 사용)
        exclude_ext_layout = QHBoxLayout()
        exclude_ext_layout.addWidget(QLabel("번역에서 제외할 확장자:"))
        self.exclude_extensions_input = QLineEdit()
        self.exclude_extensions_input.setPlaceholderText("예: jpg,png,mp3,wav (쉼표로 구분)")
        self.exclude_extensions_input.setFixedWidth(300)  # 입력창 너비 고정
        exclude_ext_layout.addWidget(self.exclude_extensions_input)
        exclude_ext_layout.addStretch(1)  # 남은 공간을 채우기 위한 스트레치 추가
        file_layout.addLayout(exclude_ext_layout)
        
        # 파일 탐색 설정 (체크박스들을 한 줄에 배치)
        file_settings_layout = QHBoxLayout()
        
        # 하위 폴더 설정
        self.include_subfolders_checkbox = QCheckBox("하위 폴더 포함")
        self.include_subfolders_checkbox.setChecked(False)
        file_settings_layout.addWidget(self.include_subfolders_checkbox)
        
        # 폴더명 번역 설정
        self.translate_folders_checkbox = QCheckBox("폴더명도 번역")
        self.translate_folders_checkbox.setChecked(False)
        file_settings_layout.addWidget(self.translate_folders_checkbox)
        
        # 나머지 공간을 채우기 위한 스트레치 추가
        file_settings_layout.addStretch(1)
        
        file_layout.addLayout(file_settings_layout)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 파일 목록 및 번역 결과 영역
        files_result_splitter = QSplitter(Qt.Vertical)
        
        # 파일 목록 트리 위젯
        files_group = QGroupBox("파일 목록 (체크된 파일만 번역)")
        files_layout = QVBoxLayout()
        
        # 전체 선택/해제 체크박스 추가
        select_all_layout = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("전체 선택/해제")
        self.select_all_checkbox.setChecked(True)  # 기본값: 체크됨
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        select_all_layout.addWidget(self.select_all_checkbox)
        select_all_layout.addStretch(1)
        files_layout.addLayout(select_all_layout)
        
        #1200 1000 800
        self.files_tree = QTreeWidget()
        self.files_tree.setHeaderLabels(["유형", "경로", "이름"])
        self.files_tree.setColumnWidth(0, 60)   # 유형 컬럼 너비 증가
        self.files_tree.setColumnWidth(1, 380)  # 경로 컬럼 너비 조정
        self.files_tree.setColumnWidth(2, 380)  # 이름 컬럼 너비 조정
        self.files_tree.setAlternatingRowColors(True)
        
        files_layout.addWidget(self.files_tree)
        files_group.setLayout(files_layout)
        
        # 번역 결과 영역
        results_splitter = QSplitter(Qt.Horizontal)
        
        # 번역된 파일명 텍스트 영역
        translated_group = QGroupBox("번역된 파일명")
        translated_layout = QVBoxLayout()
        self.translated_text = QTextEdit()
        self.translated_text.setReadOnly(True)
        translated_layout.addWidget(self.translated_text)
        translated_group.setLayout(translated_layout)
        
        results_splitter.addWidget(translated_group)
        
        # 스플리터 설정
        files_result_splitter.addWidget(files_group)
        files_result_splitter.addWidget(results_splitter)
        
        # 스플리터 크기 비율 설정
        files_result_splitter.setSizes([400, 200])
        
        main_layout.addWidget(files_result_splitter, 1)
        
        # 언어 선택 섹션
        language_group = QGroupBox("번역 언어 선택")
        language_layout = QHBoxLayout()
        
        self.language_group = QButtonGroup()
        
        self.korean_radio = QRadioButton("한국어")
        self.english_radio = QRadioButton("영어")
        self.japanese_radio = QRadioButton("일본어")
        
        self.korean_radio.setChecked(True)  # 기본값: 한국어
        
        self.language_group.addButton(self.korean_radio, 1)
        self.language_group.addButton(self.english_radio, 2)
        self.language_group.addButton(self.japanese_radio, 3)
        
        language_layout.addWidget(self.korean_radio)
        language_layout.addWidget(self.english_radio)
        language_layout.addWidget(self.japanese_radio)
        language_layout.addStretch(1)
        
        language_group.setLayout(language_layout)
        main_layout.addWidget(language_group)
        
        # 진행 상황 표시 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v/%m (%p%)")
        self.progress_bar.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.progress_bar)
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        
        self.translate_btn = QPushButton("번역하기")
        self.translate_btn.clicked.connect(self.translate_filenames)
        self.translate_btn.setMinimumHeight(40)
        
        self.apply_btn = QPushButton("적용하기")
        self.apply_btn.clicked.connect(self.apply_translations)
        self.apply_btn.setEnabled(False)  # 초기 상태: 비활성화
        self.apply_btn.setMinimumHeight(40)
        
        button_layout.addStretch(1)
        button_layout.addWidget(self.translate_btn)
        button_layout.addWidget(self.apply_btn)
        button_layout.addStretch(1)
        
        main_layout.addLayout(button_layout)
        
        # 상태 표시줄
        self.statusBar().showMessage('준비됨')
    
    def toggle_select_all(self, state):
        """전체 선택/해제 체크박스 토글 시 호출"""
        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        
        # 모든 항목의 체크 상태 변경
        root = self.files_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, check_state)
    
    def load_settings(self):
        """저장된 설정 불러오기"""
        api_key = self.settings.value("api_key", "")
        last_directory = self.settings.value("last_directory", "")
        selected_language = self.settings.value("selected_language", 1, type=int)
        chunk_size = self.settings.value("chunk_size", "10")
        delay_time = self.settings.value("delay_time", "3")
        include_subfolders = self.settings.value("include_subfolders", False, type=bool)
        exclude_extensions = self.settings.value("exclude_extensions", "")
        model_name = self.settings.value("model_name", "gemini-2.0-flash")
        custom_prompt = self.settings.value("custom_prompt", "")
        translate_folders = self.settings.value("translate_folders", False, type=bool)
        
        self.api_key_input.setText(api_key)
        self.path_input.setText(last_directory)
        self.chunk_size_input.setText(chunk_size)
        self.delay_time_input.setText(delay_time)
        self.include_subfolders_checkbox.setChecked(include_subfolders)
        self.exclude_extensions_input.setText(exclude_extensions)
        self.model_input.setText(model_name)
        self.prompt_input.setText(custom_prompt)
        self.translate_folders_checkbox.setChecked(translate_folders)
        
        # 저장된 언어 선택 적용
        if selected_language == 1:
            self.korean_radio.setChecked(True)
        elif selected_language == 2:
            self.english_radio.setChecked(True)
        elif selected_language == 3:
            self.japanese_radio.setChecked(True)
    
    def save_settings(self):
        """현재 설정 저장"""
        self.settings.setValue("api_key", self.api_key_input.text())
        self.settings.setValue("last_directory", self.path_input.text())
        self.settings.setValue("selected_language", self.language_group.checkedId())
        self.settings.setValue("chunk_size", self.chunk_size_input.text())
        self.settings.setValue("delay_time", self.delay_time_input.text())
        self.settings.setValue("include_subfolders", self.include_subfolders_checkbox.isChecked())
        self.settings.setValue("exclude_extensions", self.exclude_extensions_input.text())
        self.settings.setValue("model_name", self.model_input.text())
        self.settings.setValue("custom_prompt", self.prompt_input.toPlainText())
        self.settings.setValue("translate_folders", self.translate_folders_checkbox.isChecked())
    
    def save_api_key(self):
        """API 키 저장 버튼 클릭 시 실행"""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '경고', 'API 키를 입력하세요.')
            return
        
        self.settings.setValue("api_key", api_key)
        QMessageBox.information(self, '알림', 'API 키가 저장되었습니다.')
    
    def browse_directory(self):
        """디렉토리 찾아보기 버튼 클릭 시 실행"""
        directory = QFileDialog.getExistingDirectory(self, '디렉토리 선택', self.path_input.text())
        if directory:
            self.path_input.setText(directory)
            self.settings.setValue("last_directory", directory)
    
    def get_files(self):
        """파일 가져오기 버튼 클릭 시 실행"""
        directory_path = self.path_input.text().strip()
        if not directory_path:
            QMessageBox.warning(self, '경고', '디렉토리 경로를 입력하세요.')
            return
        
        if not os.path.isdir(directory_path):
            QMessageBox.warning(self, '경고', '유효한 디렉토리 경로가 아닙니다.')
            return
        
        try:
            # 트리 위젯 초기화
            self.files_tree.clear()
            
            # 헤더 레이블 순서 변경
            self.files_tree.setHeaderLabels(["유형", "경로", "이름"])
            self.files_tree.setColumnWidth(0, 60)   # 유형 컬럼 너비 증가
            self.files_tree.setColumnWidth(1, 380)  # 경로 컬럼 너비 조정
            self.files_tree.setColumnWidth(2, 380)  # 이름 컬럼 너비 조정
            self.files_tree.setAlternatingRowColors(True)
            
            # 제외할 확장자 목록 가져오기
            exclude_extensions_text = self.exclude_extensions_input.text().strip().lower()
            exclude_extensions = [ext.strip() for ext in exclude_extensions_text.split(',') if ext.strip()]
            
            # 디버깅용 메시지
            if exclude_extensions:
                print(f"제외할 확장자: {exclude_extensions}")
            
            # 하위 폴더 포함 여부 확인
            include_subfolders = self.include_subfolders_checkbox.isChecked()
            
            # 파일과 폴더 목록 가져오기
            files = []
            folders = []
            
            if include_subfolders:
                # 하위 폴더를 포함한 모든 파일 및 폴더 가져오기
                for root, dirs, filenames in os.walk(directory_path):
                    # 폴더 처리
                    for dirname in dirs:
                        folder_path = os.path.join(root, dirname)
                        # 전체 경로 표시
                        display_path = os.path.dirname(folder_path)
                        
                        folders.append({
                            'name': dirname,
                            'path': folder_path,
                            'display_path': display_path,
                            'type': 'folder'
                        })
                    
                    # 파일 처리
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        if os.path.isfile(file_path):
                            # 확장자 확인 (첫 번째 문자의 점을 제거)
                            _, ext = os.path.splitext(filename)
                            ext = ext.lower().lstrip('.')
                            
                            if ext in exclude_extensions:
                                print(f"제외된 파일: {filename}, 확장자: {ext}")
                                continue  # 제외된 확장자는 건너뜀
                            
                            # 전체 경로 표시 (directory_path를 기준으로)
                            display_path = os.path.dirname(file_path)
                            
                            files.append({
                                'name': filename,
                                'path': file_path,
                                'display_path': display_path,
                                'type': 'file'
                            })
            else:
                # 현재 디렉토리의 파일과 폴더만 가져오기
                for item_name in os.listdir(directory_path):
                    item_path = os.path.join(directory_path, item_name)
                    
                    # 폴더 처리
                    if os.path.isdir(item_path):
                        folders.append({
                            'name': item_name,
                            'path': item_path,
                            'display_path': directory_path,
                            'type': 'folder'
                        })
                    # 파일 처리
                    elif os.path.isfile(item_path):
                        # 확장자 확인 (첫 번째 문자의 점을 제거)
                        _, ext = os.path.splitext(item_name)
                        ext = ext.lower().lstrip('.')
                        
                        if ext in exclude_extensions:
                            print(f"제외된 파일: {item_name}, 확장자: {ext}")
                            continue  # 제외된 확장자는 건너뜀
                        
                        # 루트 디렉토리 경로 표시
                        display_path = directory_path
                        
                        files.append({
                            'name': item_name,
                            'path': item_path,
                            'display_path': display_path,
                            'type': 'file'
                        })
            
            # 폴더와 파일을 하나의 목록으로 합치기
            all_items = folders + files
            
            if not all_items:
                QMessageBox.information(self, '알림', '선택한 경로에 파일이나 폴더가 없거나 모든 파일이 제외되었습니다.')
                return
            
            # 선택된 파일 목록 업데이트
            self.selected_files = all_items
            
            # 트리 위젯에 파일 목록 추가 (유형을 앞에 표시)
            for item in all_items:
                display_path = item['display_path']
                tree_item = QTreeWidgetItem([item['type'], display_path, item['name']])
                
                # 아이콘 설정
                if item['type'] == 'folder':
                    tree_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))  # 아이콘 위치를 0번 컬럼으로 변경
                else:
                    tree_item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))  # 아이콘 위치를 0번 컬럼으로 변경
                
                tree_item.setCheckState(0, Qt.Checked)  # 체크박스는 첫 번째 컬럼에 유지
                self.files_tree.addTopLevelItem(tree_item)
            
            # 전체 선택 체크박스 상태 업데이트
            self.select_all_checkbox.setChecked(True)
            
            self.statusBar().showMessage(f'파일 {len(files)}개, 폴더 {len(folders)}개를 불러왔습니다.')
        except Exception as e:
            QMessageBox.critical(self, '오류', f'파일 목록을 불러오는 중 오류가 발생했습니다: {str(e)}')
            logger.error(f"파일 목록 불러오기 오류: {str(e)}")
    
    def get_selected_language(self):
        """선택된 언어 가져오기"""
        if self.korean_radio.isChecked():
            return "korean"
        elif self.english_radio.isChecked():
            return "english"
        elif self.japanese_radio.isChecked():
            return "japanese"
        return "korean"  # 기본값
    
    def translate_filenames(self):
        """번역하기 버튼 클릭 시 실행"""
        # 체크된 항목 목록 가져오기
        checked_items = []
        root = self.files_tree.invisibleRootItem()
        
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.Checked:
                item_type = item.text(0)  # 유형
                display_path = item.text(1)  # 경로
                item_name = item.text(2)  # 이름
                
                # selected_files 배열에서 일치하는 항목 찾기
                for file_item in self.selected_files:
                    if file_item['name'] == item_name and file_item['display_path'] == display_path and file_item['type'] == item_type:
                        checked_items.append(file_item)
                        break
        
        if not checked_items:
            QMessageBox.warning(self, '경고', '번역할 항목이 선택되지 않았습니다. 항목을 선택한 후 다시 시도하세요.')
            return
        
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '경고', 'API 키를 입력하세요.')
            return
        
        # 폴더명 번역 체크 여부 확인
        translate_folders = self.translate_folders_checkbox.isChecked()
        
        # 제외할 확장자 목록 가져오기
        exclude_extensions_text = self.exclude_extensions_input.text().strip().lower()
        exclude_extensions = [ext.strip() for ext in exclude_extensions_text.split(',') if ext.strip()]
        
        # 확장자 및 폴더 설정에 따라 항목 필터링
        excluded_items = []
        filtered_items = []
        
        for item in checked_items:
            # 폴더 처리
            if item['type'] == 'folder':
                if translate_folders:
                    filtered_items.append(item)
                else:
                    excluded_items.append(item)
                continue
                
            # 파일 처리
            filename = item['name']
            _, ext = os.path.splitext(filename)
            ext = ext.lower().lstrip('.')
            
            if ext in exclude_extensions:
                excluded_items.append(item)
            else:
                filtered_items.append(item)
        
        if not filtered_items:
            # 제외 사유 메시지 생성
            excluded_files_msg = f"제외된 파일: {len([item for item in excluded_items if item['type'] == 'file'])}개"
            excluded_folders_msg = ""
            if not translate_folders:
                excluded_folders_count = len([item for item in excluded_items if item['type'] == 'folder'])
                if excluded_folders_count > 0:
                    excluded_folders_msg = f", 제외된 폴더: {excluded_folders_count}개 (폴더명 번역 옵션 꺼짐)"
            
            QMessageBox.warning(self, '경고', f'번역할 항목이 없습니다. {excluded_files_msg}{excluded_folders_msg}')
            return
        
        # 번역 전 통계 표시
        excluded_files = [item for item in excluded_items if item['type'] == 'file']
        excluded_folders = [item for item in excluded_items if item['type'] == 'folder']
        filtered_files = [item for item in filtered_items if item['type'] == 'file']
        filtered_folders = [item for item in filtered_items if item['type'] == 'folder']
        
        excluded_files_msg = f"{len(excluded_files)}개 파일이 확장자 제외 설정으로 인해 번역에서 제외됩니다." if excluded_files else ""
        excluded_folders_msg = f"{len(excluded_folders)}개 폴더가 '폴더명 번역' 옵션이 꺼져서 제외됩니다." if excluded_folders else ""
        
        translate_msg = []
        if filtered_files:
            translate_msg.append(f"• {len(filtered_files)}개 파일을 번역합니다.")
        if filtered_folders:
            translate_msg.append(f"• {len(filtered_folders)}개 폴더명을 번역합니다.")
        
        exclude_msg = []
        if excluded_files_msg:
            exclude_msg.append(f"• {excluded_files_msg}")
        if excluded_folders_msg:
            exclude_msg.append(f"• {excluded_folders_msg}")
        
        stats_message = "총 " + str(len(checked_items)) + "개 항목 중:\n"
        stats_message += "\n".join(translate_msg)
        if exclude_msg:
            stats_message += "\n\n제외 항목:\n" + "\n".join(exclude_msg)
        
        reply = QMessageBox.information(
            self, 
            '번역 통계', 
            stats_message + "\n\n계속 진행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.No:
            return
        
        # 언어 선택 가져오기
        language = self.get_selected_language()
        
        # 번역할 항목 이름 목록 가져오기
        item_names = [item['name'] for item in filtered_items]
        
        # 설정 값 가져오기 (예외 처리 포함)
        try:
            chunk_size = int(self.chunk_size_input.text())
            if chunk_size <= 0:
                chunk_size = 10
        except ValueError:
            chunk_size = 10
            self.chunk_size_input.setText("10")
        
        try:
            delay_time = int(self.delay_time_input.text())
            if delay_time < 0:
                delay_time = 3
        except ValueError:
            delay_time = 3
            self.delay_time_input.setText("3")
        
        # 설정 정보 로깅
        logger.info(f"번역 설정 - 청크 크기: {chunk_size}, 대기 시간: {delay_time}초, 파일 수: {len(item_names)}")
        
        # 버튼 비활성화 및 상태 업데이트
        self.translate_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)
        self.statusBar().showMessage('번역 중...')
        
        # 번역 쓰레드 생성 및 시작 (설정 값 전달)
        self.translation_thread = TranslationThread(
            api_key, 
            item_names, 
            language,
            chunk_size,
            delay_time,
            self.model_input.text().strip(),
            self.prompt_input.toPlainText().strip() or None
        )
        self.translation_thread.progress_signal.connect(self.update_translation_progress)
        self.translation_thread.result_signal.connect(self.handle_translation_result)
        self.translation_thread.error_signal.connect(self.handle_translation_error)
        self.translation_thread.finished.connect(lambda: self.translate_btn.setEnabled(True))
        
        # 현재 처리 중인 항목 목록 저장 (번역 결과와 매핑하기 위함)
        self.current_processing_files = filtered_items
        
        self.translation_thread.start()
    
    def update_translation_progress(self, current, total):
        """번역 진행 상황 업데이트"""
        progress_percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress_percent)
        self.progress_bar.setFormat(f"{current}/{total} ({progress_percent}%)")
        self.statusBar().showMessage(f'번역 중... {current}/{total}')
    
    def handle_translation_result(self, translations):
        """번역 결과 처리"""
        if not translations:
            QMessageBox.warning(self, '경고', '번역 결과가 없습니다.')
            return
        
        # 번역 결과 저장 (윈도우 호환성을 위한 처리 포함)
        self.translated_filenames = {}
        display_text = ''
        
        for item in translations:
            original_name = item['original']
            
            # 현재 처리 중인 항목 찾기
            current_item = None
            for proc_item in self.current_processing_files:
                if proc_item['name'] == original_name:
                    current_item = proc_item
                    break
            
            if not current_item:
                continue
            
            # 항목 유형에 따른 처리
            item_type = current_item['type']
            
            # 번역된 이름 정규화
            translated_name = unicodedata.normalize('NFKC', item['translated'])
            
            # 윈도우에서 사용할 수 없는 특수문자 처리
            forbidden_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|', '？', '！', '；', '：']
            for char in forbidden_chars:
                translated_name = translated_name.replace(char, '_')
            
            # 하위 폴더 구조 유지 (파일인 경우)
            if item_type == 'file' and os.path.sep in original_name:
                dirname, basename = os.path.split(original_name)
                # 번역 대상은 파일명만
                translated_name = os.path.join(dirname, translated_name)
            
            # 정제된 이름 저장
            self.translated_filenames[original_name] = {
                'new_name': translated_name,
                'type': item_type,
                'path': current_item['path']
            }
            
            # 원본 이름과 번역된 이름을 함께 표시
            type_icon = "📁 " if item_type == "folder" else "📄 "
            display_text += f"{type_icon}{original_name} → {translated_name}\n"
        
        # 결과 표시
        self.translated_text.setText(display_text)
        self.apply_btn.setEnabled(True)
        
        # 상태 업데이트
        self.progress_bar.setValue(100)
        self.statusBar().showMessage(f'번역 완료. {len(translations)}개 항목이 번역되었습니다.')
        
        # 완료 알림
        QMessageBox.information(self, '알림', f'번역이 완료되었습니다. {len(translations)}개 항목이 번역되었습니다.')
    
    def handle_translation_error(self, error_message):
        """번역 오류 처리"""
        QMessageBox.critical(self, '오류', f'번역 중 오류가 발생했습니다: {error_message}')
        self.statusBar().showMessage('번역 오류 발생')
    
    def apply_translations(self):
        """적용하기 버튼 클릭 시 실행"""
        if not self.translated_filenames:
            QMessageBox.warning(self, '경고', '적용할 번역 결과가 없습니다.')
            return
        
        if not hasattr(self, 'current_processing_files') or not self.current_processing_files:
            QMessageBox.warning(self, '경고', '번역된 파일 정보가 없습니다. 다시 번역해주세요.')
            return
        
        # 변경할 항목 목록 준비
        items_to_rename = []
        
        for item in self.current_processing_files:
            original_name = item['name']
            if original_name in self.translated_filenames:
                translated_info = self.translated_filenames[original_name]
                items_to_rename.append({
                    'original_path': item['path'],
                    'new_name': translated_info['new_name'],
                    'type': translated_info['type']
                })
        
        if not items_to_rename:
            QMessageBox.warning(self, '경고', '변경할 항목이 없습니다.')
            return
        
        # 항목 유형 별로 카운트
        files_count = len([item for item in items_to_rename if item['type'] == 'file'])
        folders_count = len([item for item in items_to_rename if item['type'] == 'folder'])
        
        # 확인 메시지 표시
        files_msg = f"{files_count}개 파일" if files_count > 0 else ""
        folders_msg = f"{folders_count}개 폴더" if folders_count > 0 else ""
        
        if files_count > 0 and folders_count > 0:
            items_msg = f"{files_msg}과 {folders_msg}"
        else:
            items_msg = files_msg + folders_msg
        
        reply = QMessageBox.question(
            self, 
            '확인', 
            f'{items_msg}의 이름을 변경하시겠습니까?',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 버튼 비활성화
        self.apply_btn.setEnabled(False)
        self.translate_btn.setEnabled(False)
        
        # 상태 업데이트
        self.progress_bar.setValue(0)
        self.statusBar().showMessage('파일명 변경 중...')
        
        # 이름 변경 쓰레드 생성 및 시작
        self.rename_thread = RenameThread(items_to_rename)
        self.rename_thread.progress_signal.connect(self.update_rename_progress)
        self.rename_thread.result_signal.connect(self.handle_rename_result)
        self.rename_thread.error_signal.connect(self.handle_rename_error)
        self.rename_thread.finished.connect(lambda: self.translate_btn.setEnabled(True))
        
        self.rename_thread.start()
    
    def update_rename_progress(self, current, total):
        """이름 변경 진행 상황 업데이트"""
        progress_percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress_percent)
        self.progress_bar.setFormat(f"{current}/{total} ({progress_percent}%)")
        self.statusBar().showMessage(f'파일명 변경 중... {current}/{total}')
    
    def handle_rename_result(self, renamed_items):
        """이름 변경 결과 처리"""
        if not renamed_items:
            QMessageBox.warning(self, '경고', '파일명 변경 결과가 없습니다.')
            return
        
        # 초기화
        self.current_processing_files = []
        self.translated_filenames = {}
        self.translated_text.clear()
        
        # 폴더와 파일 개수 확인
        renamed_files = [item for item in renamed_items if item['type'] == 'file']
        renamed_folders = [item for item in renamed_items if item['type'] == 'folder']
        
        # 상세 로그 추가
        for folder in renamed_folders:
            logger.info(f"폴더 이름 변경 완료: {folder['original_path']} -> {folder['new_path']}")
        
        # 상태 업데이트
        status_message = []
        if renamed_files:
            status_message.append(f"{len(renamed_files)}개 파일")
        if renamed_folders:
            status_message.append(f"{len(renamed_folders)}개 폴더")
        
        status_text = " 및 ".join(status_message) + "의 이름이 변경되었습니다."
        self.statusBar().showMessage(f'이름 변경 완료. {status_text}')
        
        # 완료 알림
        QMessageBox.information(self, '알림', f'이름 변경이 완료되었습니다. {status_text}')
        
        # 변경된 디렉토리의 파일 목록 다시 가져오기
        self.get_files()
    
    def handle_rename_error(self, error_message):
        """이름 변경 오류 처리"""
        QMessageBox.critical(self, '오류', f'파일명 변경 중 오류가 발생했습니다: {error_message}')
        self.statusBar().showMessage('파일명 변경 오류 발생')
        self.apply_btn.setEnabled(True)  # 버튼 다시 활성화
    
    def closeEvent(self, event):
        """앱 종료 시 설정 저장"""
        self.save_settings()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 모던한 스타일 적용
    
    # 폰트 설정 (선택 사항)
    font = QFont("맑은 고딕", 9)
    app.setFont(font)
    
    # 앱 시작
    window = TranslationApp()
    window.show()
    sys.exit(app.exec_())
