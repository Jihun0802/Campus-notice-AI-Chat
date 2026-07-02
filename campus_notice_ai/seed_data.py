from __future__ import annotations


MOBILE_SYSTEMS_SOURCE = {
    "name": "단국대학교 모바일시스템공학과 수동 등록",
    "source_type": "manual",
    "base_url": "mock://dku/mobile-systems",
    "department": "모바일시스템공학과",
}


SEED_NOTICES = [
    {
        "title": "모바일시스템공학과 2026학년도 졸업시험 신청 안내",
        "body_text": (
            "2026학년도 8월 졸업예정자를 대상으로 모바일시스템공학과 졸업시험 신청을 받습니다.\n"
            "신청 대상은 4학년 재학생 및 수료생 중 졸업시험 응시가 필요한 학생입니다.\n"
            "신청 기간은 2026년 6월 26일부터 2026년 7월 3일까지이며, 학과 사무실 이메일로 신청서를 제출해야 합니다.\n"
            "시험 과목은 전공기초, 모바일프로그래밍, 네트워크, 데이터베이스 영역으로 구성됩니다.\n"
            "기한 내 신청하지 않은 학생은 이번 회차 시험 응시가 제한될 수 있습니다."
        ),
        "publisher": "모바일시스템공학과 사무실",
        "category": "졸업",
        "department": "모바일시스템공학과",
        "grade": "4",
        "course_id": None,
        "visibility": "department",
        "published_at": "2026-06-26",
        "deadline_at": "2026-07-03",
        "original_url": "mock://dku/mobile-systems/notice/graduation-exam-2026",
    },
    {
        "title": "2026학년도 2학기 휴학 및 복학 신청 기간 안내",
        "body_text": (
            "2026학년도 2학기 휴학 및 복학 신청 기간을 안내합니다.\n"
            "일반 휴학, 군 휴학, 질병 휴학 및 복학 예정 학생은 학교 포털의 학적 메뉴에서 신청할 수 있습니다.\n"
            "신청 기간은 2026년 7월 1일부터 2026년 7월 15일까지입니다.\n"
            "장학금 수혜 예정자와 졸업예정자는 신청 전 반드시 학과 사무실 또는 학사팀에 상담해야 합니다."
        ),
        "publisher": "학사팀",
        "category": "학사",
        "department": None,
        "grade": None,
        "course_id": None,
        "visibility": "public",
        "published_at": "2026-06-24",
        "deadline_at": "2026-07-15",
        "original_url": "mock://dku/school/notice/leave-return-2026-fall",
    },
    {
        "title": "모바일시스템공학과 캡스톤디자인 최종 발표 일정 안내",
        "body_text": (
            "모바일시스템공학과 캡스톤디자인 최종 발표를 2026년 7월 8일에 진행합니다.\n"
            "발표 대상은 캡스톤디자인 수강 팀 전체이며, 팀별 발표 시간은 10분, 질의응답은 5분입니다.\n"
            "발표 자료는 2026년 7월 6일 18시까지 LMS 과제함에 제출해야 합니다.\n"
            "발표 순서와 강의실은 추후 학과 공지로 다시 안내됩니다."
        ),
        "publisher": "모바일시스템공학과",
        "category": "수업",
        "department": "모바일시스템공학과",
        "grade": "4",
        "course_id": "capstone-design",
        "visibility": "course",
        "published_at": "2026-06-20",
        "deadline_at": "2026-07-06",
        "original_url": "mock://dku/mobile-systems/notice/capstone-final-presentation-2026",
    },
    {
        "title": "2026학년도 2학기 성적우수 장학금 신청 안내",
        "body_text": (
            "2026학년도 2학기 성적우수 장학금 신청을 받습니다.\n"
            "신청 대상은 직전 학기 12학점 이상 이수하고 평점 기준을 충족한 재학생입니다.\n"
            "신청자는 장학 신청서와 개인정보 활용 동의서를 2026년 7월 10일까지 제출해야 합니다.\n"
            "학과 추천 장학은 학과 내부 심사를 거쳐 선발되며, 최종 선발 여부는 장학팀 공지로 확인할 수 있습니다."
        ),
        "publisher": "장학팀",
        "category": "장학",
        "department": None,
        "grade": None,
        "course_id": None,
        "visibility": "public",
        "published_at": "2026-06-22",
        "deadline_at": "2026-07-10",
        "original_url": "mock://dku/scholarship/notice/merit-scholarship-2026-fall",
    },
    {
        "title": "컴퓨터네트워크 기말 과제 제출 안내",
        "body_text": (
            "컴퓨터네트워크 수강생은 기말 과제를 2026년 7월 3일 23시 59분까지 LMS에 제출해야 합니다.\n"
            "과제 주제는 TCP 혼잡 제어 분석이며, 보고서는 PDF 형식으로 제출합니다.\n"
            "소스 코드가 있는 경우 ZIP 파일로 함께 첨부해야 합니다.\n"
            "지각 제출은 하루당 10점 감점되며, 표절이 확인되면 학칙에 따라 처리됩니다."
        ),
        "publisher": "컴퓨터네트워크 담당교수",
        "category": "과제",
        "department": "모바일시스템공학과",
        "grade": "3",
        "course_id": "computer-network",
        "visibility": "course",
        "published_at": "2026-06-26",
        "deadline_at": "2026-07-03",
        "original_url": "mock://dku/lms/mobile-systems/computer-network/final-assignment-2026",
    },
    {
        "title": "2026학년도 여름 계절학기 수강신청 정정 기간 안내",
        "body_text": (
            "2026학년도 여름 계절학기 수강신청 정정 기간은 2026년 6월 29일부터 2026년 6월 30일까지입니다.\n"
            "정정 기간에는 잔여석이 있는 교과목에 한해 수강신청 변경이 가능합니다.\n"
            "수강 취소 후 재신청하지 못하는 경우가 발생할 수 있으므로 변경 전 잔여석을 반드시 확인해야 합니다.\n"
            "등록금 환불 기준은 학사 공지의 계절학기 운영 안내를 따릅니다."
        ),
        "publisher": "학사팀",
        "category": "수강신청",
        "department": None,
        "grade": None,
        "course_id": None,
        "visibility": "public",
        "published_at": "2026-06-23",
        "deadline_at": "2026-06-30",
        "original_url": "mock://dku/school/notice/summer-course-change-2026",
    },
    {
        "title": "모바일시스템공학과 졸업논문 및 졸업요건 확인 안내",
        "body_text": (
            "2026학년도 8월 졸업예정자는 졸업논문 제출 여부와 전공 학점, 교양 학점, 비교과 이수 기준을 확인해야 합니다.\n"
            "졸업요건 확인 기간은 2026년 7월 1일부터 2026년 7월 12일까지입니다.\n"
            "확인 결과 이상이 있는 학생은 학과 사무실에 즉시 문의해야 하며, 기간 이후에는 정정이 어려울 수 있습니다.\n"
            "졸업논문 대체 요건을 적용받는 학생은 증빙 자료를 함께 제출해야 합니다."
        ),
        "publisher": "모바일시스템공학과 사무실",
        "category": "졸업",
        "department": "모바일시스템공학과",
        "grade": "4",
        "course_id": None,
        "visibility": "department",
        "published_at": "2026-06-25",
        "deadline_at": "2026-07-12",
        "original_url": "mock://dku/mobile-systems/notice/graduation-requirements-check-2026",
    },
    {
        "title": "2026학년도 하계 현장실습 신청 안내",
        "body_text": (
            "2026학년도 하계 현장실습 참여 학생을 모집합니다.\n"
            "신청 대상은 3학년 이상 재학생이며, 실습 기간은 2026년 7월 20일부터 2026년 8월 21일까지입니다.\n"
            "참여를 희망하는 학생은 이력서와 자기소개서를 2026년 7월 5일까지 현장실습지원센터 시스템에 제출해야 합니다.\n"
            "기업별 선발 기준이 다르므로 모집 공고의 전공, 근무지, 실습지원비 조건을 확인해야 합니다."
        ),
        "publisher": "현장실습지원센터",
        "category": "현장실습",
        "department": None,
        "grade": "3",
        "course_id": None,
        "visibility": "grade",
        "published_at": "2026-06-21",
        "deadline_at": "2026-07-05",
        "original_url": "mock://dku/career/notice/summer-internship-2026",
    },
    {
        "title": "모바일시스템공학과 사무실 운영 시간 변경 안내",
        "body_text": (
            "모바일시스템공학과 사무실 운영 시간이 방학 기간 동안 변경됩니다.\n"
            "변경 기간은 2026년 7월 1일부터 2026년 8월 31일까지이며, 운영 시간은 평일 10시부터 16시까지입니다.\n"
            "점심시간은 12시부터 13시까지이며, 해당 시간에는 방문 상담이 제한됩니다.\n"
            "긴급 문의는 학과 대표 이메일로 접수하면 순차적으로 답변합니다."
        ),
        "publisher": "모바일시스템공학과 사무실",
        "category": "학과운영",
        "department": "모바일시스템공학과",
        "grade": None,
        "course_id": None,
        "visibility": "department",
        "published_at": "2026-06-27",
        "deadline_at": None,
        "original_url": "mock://dku/mobile-systems/notice/office-hours-summer-2026",
    },
    {
        "title": "모바일 앱 보안 전공 비교과 프로그램 신청 안내",
        "body_text": (
            "모바일시스템공학과 전공 비교과 프로그램으로 모바일 앱 보안 실습 특강을 운영합니다.\n"
            "특강은 2026년 7월 11일 13시부터 17시까지 진행되며, Android 앱 취약점 분석과 보안 점검 실습을 다룹니다.\n"
            "신청 대상은 모바일시스템공학과 재학생이며, 선착순 30명을 모집합니다.\n"
            "참여 신청은 2026년 7월 8일까지 학과 비교과 신청 폼으로 제출해야 합니다."
        ),
        "publisher": "모바일시스템공학과",
        "category": "비교과",
        "department": "모바일시스템공학과",
        "grade": None,
        "course_id": "mobile-app-security-workshop",
        "visibility": "department",
        "published_at": "2026-06-28",
        "deadline_at": "2026-07-08",
        "original_url": "mock://dku/mobile-systems/notice/mobile-app-security-workshop-2026",
    },
]
