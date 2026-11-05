on run argv
    set deckPath to item 1 of argv
    set rows to paragraphs of (read POSIX file (item 2 of argv) as «class utf8»)
    set deckName to item 3 of argv
    set deckStem to item 4 of argv
    set pageNumbers to {}
    set queues to {}
    set lastPage to 0
    set AppleScript's text item delimiters to tab
    repeat with rowText in rows
        if (contents of rowText) is not "" then
            set fields to text items of (contents of rowText)
            set pageNumber to (item 1 of fields) as integer
            if pageNumber is not lastPage then
                set end of pageNumbers to pageNumber
                set end of queues to {}
                set lastPage to pageNumber
            end if
            set pendingItems to last item of queues
            set end of pendingItems to {item 2 of fields, (item 3 of fields) as real}
            set last item of queues to pendingItems
        end if
    end repeat
    set AppleScript's text item delimiters to ""

    tell application id "com.microsoft.Powerpoint"
        open (POSIX file deckPath)
        activate
    end tell
    repeat 150 times
        tell application "System Events"
            set inFront to frontmost of (first application process whose bundle identifier is "com.microsoft.Powerpoint")
        end tell
        if inFront then exit repeat
        delay 0.2
    end repeat
    if not inFront then error "PowerPoint did not come to the foreground."

    set pendingPages to count pageNumbers
    tell application id "com.microsoft.Powerpoint"
        if name of active presentation is not in {deckName, deckStem} then error "Preview is not the active presentation."
        if pendingPages > 0 then go to slide (view of active window) number (item 1 of pageNumbers)
    end tell
    repeat while pendingPages > 0
        set currentPage to 0
        tell application id "com.microsoft.Powerpoint"
            if (count of presentations) is 0 then error "The preview was closed before output finished."
            if not (exists (presentation deckName)) and not (exists (presentation deckStem)) then error "The preview was closed before output finished."
            if name of active presentation is in {deckName, deckStem} then
                set currentPage to my selectedPage()
            end if
        end tell
        set queueIndex to 0
        repeat with i from 1 to (count pageNumbers)
            if item i of pageNumbers is currentPage then
                set queueIndex to i
                exit repeat
            end if
        end repeat
        set pendingItems to {}
        if queueIndex > 0 then set pendingItems to item queueIndex of queues
        if pendingItems is {} then
            delay 0.12
        else
            set {objectName, originalLeft} to item 1 of pendingItems
            tell application id "com.microsoft.Powerpoint"
                set previewShape to shape objectName of slide currentPage of active presentation
                set left position of previewShape to originalLeft
                set placementError to (left position of previewShape) - originalLeft
                if placementError > 0.1 or placementError < -0.1 then error "Could not restore preview element."
            end tell
            set pendingItems to rest of pendingItems
            set item queueIndex of queues to pendingItems
            delay 0.5
            if pendingItems is {} then
                set pendingPages to pendingPages - 1
                if pendingPages > 0 then
                    tell application id "com.microsoft.Powerpoint"
                        if (name of active presentation is in {deckName, deckStem}) and (my selectedPage() is currentPage) then
                            repeat with stepNumber from 1 to ((count pageNumbers) - 1)
                                set j to ((queueIndex + stepNumber - 1) mod (count pageNumbers)) + 1
                                if item j of queues is not {} then
                                    go to slide (view of active window) number (item j of pageNumbers)
                                    exit repeat
                                end if
                            end repeat
                        end if
                    end tell
                end if
            end if
        end if
    end repeat
    return "CELL_PPT_OUTPUT_COMPLETE"
end run

on selectedPage()
    tell application id "com.microsoft.Powerpoint"
        try
            return slide index of slide of view of active window
        on error
            try
                return slide index of slide range of selection of active window
            on error
                return 0
            end try
        end try
    end tell
end selectedPage
